"""Утилиты: ANSI-цвета, JSONC-парсер, бэкапы, fzf, константы."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime

from rb_tui import console, paths

CONFIG = paths.discover_config()
CACHE = paths.cache_dir()
STATE = os.path.join(CACHE, "catalog-state.json")
MISSING = os.path.join(CACHE, "missing.json")
LOG = os.path.join(CACHE, "auto-sync.log")
METRICS_HISTORY = os.path.join(CACHE, "metrics-history.json")
METRICS_LOG = os.path.join(CACHE, "metrics-history.jsonl")
TAGS_FILE = os.path.join(CACHE, "tags.json")
# В metrics.json держим только «горячий» хвост для быстрых запросов.
# Полная история пишется в METRICS_LOG (JSONL) и живёт до --prune-metrics.
MAX_HISTORY = 200

# Инициализация консоли и каталога кеша отложена: один импорт не должен
# переконфигурировать stdio и писать на диск.
ANSI = False
COLOR = False
INTERACTIVE = False
_SETUP_DONE = False


def ensure_setup():
    """Подготовить консоль и каталог кеша один раз при запуске приложения."""
    global _SETUP_DONE, ANSI, COLOR, INTERACTIVE
    if _SETUP_DONE:
        return
    _SETUP_DONE = True
    os.makedirs(CACHE, exist_ok=True)
    ANSI = console.setup()
    COLOR = ANSI and console.can_color() and os.environ.get("NO_COLOR") is None
    INTERACTIVE = sys.stdin.isatty() and sys.stdout.isatty()


def get_config():
    """Единственный источник пути к конфигу (--config меняет его)."""
    return CONFIG


def set_config(path):
    """Задать путь к конфигу для всего процесса."""
    global CONFIG
    CONFIG = path


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


def check_url(url, allowed=("http", "https")):
    """Отклонить file:// и прочие схемы до запроса, а не внутри urllib."""
    text = str(url or "")
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme not in allowed or not parsed.netloc:
        raise ValueError(f"недопустимый URL: {text!r}")
    return text


# ── Атомарная запись ──

def _replace_with_retry(src, dst, attempts=3):
    """os.replace с повторами: на Windows файл бывает занят антивирусом."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError as e:
            if attempt == attempts - 1:
                raise OSError(
                    f"не удалось перезаписать {dst}: файл занят другой программой"
                ) from e
            time.sleep(0.15 * (attempt + 1))


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
        _replace_with_retry(tmp, path)
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
        _replace_with_retry(tmp, dst)
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

def backup_prefix():
    """Имя бэкапа зависит от конфига: opencode.json.bak- или opencode.jsonc.bak-."""
    return os.path.basename(CONFIG) + ".bak-"


def backup_config():
    bak = CONFIG + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    shutil.copy2(CONFIG, bak)
    return bak


def prune_backups(days=30, dry_run=False):
    """Удалить бэкапы старше N дней."""
    now = datetime.now().timestamp()
    cutoff = now - days * 86400
    removed = 0
    directory = os.path.dirname(CONFIG) or "."
    prefix = backup_prefix()
    for fname in os.listdir(directory):
        if not fname.startswith(prefix):
            continue
        fpath = os.path.join(directory, fname)
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
    prefix = backup_prefix()
    directory = os.path.dirname(CONFIG) or "."
    return len([f for f in os.listdir(directory) if f.startswith(prefix)])


# ── fzf ──

def fzf_multi(items, header, prompt):
    """Выбрать несколько элементов. fzf, а без него — нумерованный список."""
    if not items:
        return []
    if shutil.which("fzf") is None:
        return _numbered_pick(items, header, prompt)
    p = subprocess.run(
        ["fzf", "-m", "--prompt", prompt, "--header", header,
         "--height", "~80%", "--border", "--reverse"],
        input="\n".join(items), text=True, capture_output=True)
    if p.returncode != 0:
        return []
    return [l.strip() for l in p.stdout.splitlines() if l.strip()]


def parse_selection(raw, count):
    """Разобрать ввод вида `1,3,5`, `2-4`, `all` в список индексов (0-based)."""
    raw = (raw or "").strip().lower()
    if not raw:
        return []
    if raw in ("all", "все", "*"):
        return list(range(count))
    picked = []
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        start, sep, end = part.partition("-")
        if sep and start.isdigit() and end.isdigit():
            bounds = (int(start), int(end))
        elif part.isdigit():
            bounds = (int(part), int(part))
        else:
            continue
        for number in range(min(bounds), max(bounds) + 1):
            if 1 <= number <= count and number - 1 not in picked:
                picked.append(number - 1)
    return picked


def _numbered_pick(items, header, prompt):
    """Fallback без fzf: те же элементы, выбор номерами."""
    if not sys.stdin.isatty():
        print(y("  fzf не установлен, а ввод не интерактивный — выбор пропущен"))
        print(dim("  установи fzf или запусти в терминале"))
        return []
    print(dim("  " + header))
    for number, item in enumerate(items, 1):
        print(f"  {number:>3}. {item}")
    print(dim("  номера через запятую (1,3,5), диапазон 2-4, all — всё, "
              "пусто — отмена"))
    try:
        raw = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return []
    return [items[index] for index in parse_selection(raw, len(items))]


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
