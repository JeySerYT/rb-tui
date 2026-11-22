"""Утилиты: ANSI-цвета, JSONC-парсер, бэкапы, fzf, константы."""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime

HOME = os.path.expanduser("~")
CONFIG = os.path.join(HOME, ".config/opencode/opencode.json")
CACHE = os.path.join(HOME, ".config/reformboss-tui")
STATE = os.path.join(CACHE, "catalog-state.json")
MISSING = os.path.join(CACHE, "missing.json")
LOG = os.path.join(CACHE, "auto-sync.log")
METRICS_HISTORY = os.path.join(CACHE, "metrics-history.json")
METRICS_LOG = os.path.join(CACHE, "metrics-history.jsonl")
TAGS_FILE = os.path.join(CACHE, "tags.json")
# В metrics.json держим только «горячий» хвост для быстрых запросов.
# Полная история пишется в METRICS_LOG (JSONL) и живёт до --prune-metrics.
MAX_HISTORY = 200

os.makedirs(CACHE, exist_ok=True)

COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
INTERACTIVE = sys.stdin.isatty() and sys.stdout.isatty()

if os.name == "nt" and COLOR:
    os.system("")


# ── ANSI colors ──

def c(txt, code):
    return f"\033[{code}m{txt}\033[0m" if COLOR else str(txt)

def g(t): return c(t, "32")
def r(t): return c(t, "31")
def y(t): return c(t, "33")
def bl(t): return c(t, "34")
def cy(t): return c(t, "36")
def dim(t): return c(t, "2")
def bold(t): return c(t, "1")


# ── JSONC: разбор с комментариями ──

def strip_jsonc(text):
    out, i, n, ins = [], 0, len(text), False
    while i < n:
        ch = text[i]
        if ins:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                ins = False
            i += 1
            continue
        if ch == '"':
            ins = True
            out.append(ch)
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            if ch in "}]":
                # JSONC/JSON5 допускает висячую запятую перед закрывающей скобкой.
                j = len(out) - 1
                while j >= 0 and out[j].isspace():
                    j -= 1
                if j >= 0 and out[j] == ",":
                    del out[j]
            out.append(ch)
            i += 1
    return "".join(out)


def parse_ok(raw):
    try:
        json.loads(strip_jsonc(raw))
        return True
    except Exception:
        return False


def pretty_name(mid):
    return mid.replace("-", " ").replace(".", " ").title()


# ── Атомарная запись ──

def atomic_write(path, text):
    """Записать файл атомарно: tmp в том же каталоге + os.replace.

    Прерывание процесса или нехватка места не оставят обрезанный JSON,
    а читатель никогда не увидит файл в промежуточном состоянии.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        if os.path.exists(path):
            # Сохранить права исходного файла (mkstemp создаёт 0600).
            try:
                os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode))
            except OSError:
                pass
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_copy(src, dst):
    """Атомарно скопировать файл (для rollback конфига)."""
    directory = os.path.dirname(dst) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_jsonl(path, entry):
    """Дописать одну строку в JSONL. Для одного писателя этого достаточно."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


# ── Бэкапы ──

def backup_config():
    bak = CONFIG + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CONFIG, bak)
    return bak


def prune_backups(days=30, dry_run=False):
    """Удалить бэкапы старше N дней."""
    now = datetime.now().timestamp()
    cutoff = now - days * 86400
    removed = 0
    for fname in os.listdir(os.path.dirname(CONFIG)):
        if not fname.startswith("opencode.json.bak-"):
            continue
        fpath = os.path.join(os.path.dirname(CONFIG), fname)
        try:
            ftime = os.path.getmtime(fpath)
            if ftime < cutoff:
                if dry_run:
                    print(f"  [dry-run] удалил бы: {fpath}")
                else:
                    os.remove(fpath)
                removed += 1
        except OSError:
            pass
    return removed


def backup_count():
    """Сколько бэкапов существует."""
    return len([f for f in os.listdir(os.path.dirname(CONFIG))
                if f.startswith("opencode.json.bak-")])


# ── fzf ──

def fzf_multi(items, header, prompt):
    if not items:
        return []
    if shutil.which("fzf") is None:
        print(y("fzf не установлен (apt install fzf / pacman -S fzf)"))
        return []
    p = subprocess.run(
        ["fzf", "-m", "--prompt", prompt, "--header", header,
         "--height", "~80%", "--border", "--reverse"],
        input="\n".join(items), text=True, capture_output=True)
    if p.returncode != 0:
        return []
    return [l.strip() for l in p.stdout.splitlines() if l.strip()]


# ── Тэги моделей ──

def load_tags():
    try:
        with open(TAGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_tags(tags):
    atomic_write(TAGS_FILE, json.dumps(tags, ensure_ascii=False, indent=2))


def set_tag(model_id, tag):
    tags = load_tags()
    if tag:
        tags[model_id] = tag
    else:
        tags.pop(model_id, None)
    save_tags(tags)
