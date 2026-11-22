"""Непредвиденная ошибка → отчёт → Issue на GitHub по шаблону.

В публичный бинарник нельзя вшить GitHub-токен: его вытащат и забанят.
Поэтому отчёт не отправляется тайно. При падении rb-tui сохраняет
диагностику, вычищает секреты и открывает браузер с уже заполненной формой
`issues/new?template=bug_report.md`. Пользователю остаётся нажать «Create».
"""

import locale
import os
import platform
import re
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from datetime import datetime

from rb_tui import __version__
from rb_tui.utils import CACHE

TEMPLATE = "bug_report.md"
KEEP_REPORTS = 3
MAX_URL = 7000
REPORT_PREFIX = "crash-"

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_SECRET_PATTERNS = (
    (re.compile(r"(?i)(api[_-]?key\"?\s*[:=]\s*\"?)([^\s\"',}]+)"), r"\1<скрыто>"),
    (re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{8,})"), r"\1<скрыто>"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), "sk-<скрыто>"),
    (re.compile(r"(?i)https?://[^\s\"'<>]*(?:token|secret|webhook)[^\s\"'<>]*"),
     "<ссылка с секретом скрыта>"),
    # У Slack токен лежит в пути, но в URL нет слов token/secret/webhook.
    (re.compile(r"(?i)https?://[^\s\"'<>]*(?:hooks\.slack\.com|api\.telegram\.org/bot)[^\s\"'<>]*"),
     "<ссылка с секретом скрыта>"),
)

_installed = False


def repo():
    from rb_tui import update

    return update.repo()


# ── санитайзер ──

def sanitize(text):
    """Убрать ANSI-коды, ключи, токены и домашний путь из отчёта."""
    value = _ANSI.sub("", str(text or ""))
    for pattern, replacement in _SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    home = os.path.expanduser("~")
    if home and home != "/":
        value = value.replace(home, "~")
    return value


def _short(value, limit=200):
    return sanitize(value)[:limit]


def _masked_argv(argv):
    """Не сохранять в отчёте значение --webhook: в нём может быть токен."""
    out = []
    mask_next = False
    for arg in argv:
        if mask_next:
            out.append("<скрыто>")
            mask_next = False
        elif arg == "--webhook":
            out.append(arg)
            mask_next = True
        elif arg.startswith("--webhook="):
            out.append("--webhook=<скрыто>")
        else:
            out.append(arg)
    return out


# ── диагностика ──

def diag_block(exc_type=None, exc=None, tb=None):
    """Текстовая диагностика для отчёта и команды --diag."""
    from rb_tui import utils

    stdout = getattr(sys.stdout, "encoding", "?") or "?"
    try:
        tty = bool(sys.stdout.isatty())
    except Exception:
        tty = False
    lines = [
        f"версия: {__version__}",
        f"запуск: {'бинарник' if getattr(sys, 'frozen', False) else 'исходники'}",
        f"ОС: {platform.platform()} ({platform.machine()})",
        f"Python: {platform.python_version()}",
        f"конфиг: {utils.CONFIG}",
        f"конфиг найден: {'да' if os.path.isfile(utils.CONFIG) else 'нет'}",
        f"кеш: {utils.CACHE}",
        f"stdout: {stdout}, tty={tty}",
        f"локаль: {locale.getpreferredencoding(False)}",
        f"команда: {' '.join(_masked_argv(sys.argv))}",
    ]
    if exc_type is not None:
        lines.append(f"исключение: {exc_type.__name__}: {exc}")
        formatted = "".join(traceback.format_exception(exc_type, exc, tb))
        tail = formatted.strip().splitlines()[-30:]
        lines.extend(["traceback:", *tail])
    return sanitize("\n".join(lines))


def diagnostics_text():
    """Вывод `--diag`: без сети и без разбора конфига."""
    return diag_block()


# ── отчёт и ссылка ──

def issue_title(exc_type=None, exc=None):
    if exc_type is None:
        return "Отчёт об ошибке rb-tui"
    return _short(f"[{platform.system()}] {exc_type.__name__}: {exc}", 120)


def format_body(exc_type, exc, tb=None):
    error = _short(f"{exc_type.__name__}: {exc}", 300)
    return "\n".join([
        "### Что случилось",
        "",
        f"`{error}`",
        "",
        "### Как повторить",
        "",
        "1. _(добавь шаги, если знаешь)_",
        "",
        "### Ожидалось",
        "",
        "_(что должно было произойти)_",
        "",
        "### Диагностика",
        "",
        "```text",
        diag_block(exc_type, exc, tb),
        "```",
    ])


def build_url(title, body):
    """Ссылка на форму нового Issue с заполненными полями.

    GitHub отклоняет слишком длинные URL, поэтому тело аккуратно укорачиваем.
    """
    limit = MAX_URL
    while True:
        query = urllib.parse.urlencode(
            {"template": TEMPLATE, "title": title, "body": body},
            quote_via=urllib.parse.quote,
        )
        url = f"https://github.com/{repo()}/issues/new?{query}"
        if len(url) <= limit or len(body) <= 400:
            return url
        body = body[: int(len(body) * 0.8)] + "\n\n…отчёт обрезан"


def report_path(stamp=None):
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return os.path.join(CACHE, f"{REPORT_PREFIX}{stamp}.log")


def write_report(body):
    """Сохранить отчёт в кеш и оставить три последних."""
    os.makedirs(CACHE, exist_ok=True)
    path = report_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write(body.rstrip() + "\n")
    _prune_reports()
    return path


def _prune_reports(keep=KEEP_REPORTS):
    try:
        names = sorted(
            (n for n in os.listdir(CACHE) if n.startswith(REPORT_PREFIX)),
            reverse=True,
        )
    except OSError:
        return
    for name in names[keep:]:
        try:
            os.unlink(os.path.join(CACHE, name))
        except OSError:
            pass


def last_report():
    try:
        names = sorted(
            (n for n in os.listdir(CACHE) if n.startswith(REPORT_PREFIX)),
            reverse=True,
        )
    except OSError:
        return None
    return os.path.join(CACHE, names[0]) if names else None


def open_issue(url):
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


# ── обработка падения ──

def _can_prompt():
    if os.environ.get("RB_TUI_NO_REPORT_PROMPT"):
        return False
    try:
        return bool(sys.stdin and sys.stdin.isatty() and sys.stderr.isatty())
    except Exception:
        return False


def _prompt(url, body):
    print("  [Enter] открыть Issue на GitHub с заполненным отчётом")
    print("  [v]     показать отчёт")
    print("  [n]     выйти без отчёта")
    while True:
        try:
            answer = input("  выбор: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer in ("", "y", "д"):
            if open_issue(url):
                print("  браузер открыт: проверь вкладку и нажми «Create»")
            else:
                print(f"  браузер не открылся. Ссылка: {url}")
            return
        if answer in ("v", "п"):
            print()
            print(body)
            return
        if answer in ("n", "no", "н"):
            return
        print("  Enter — открыть, v — показать, n — выйти")


def handle(exc_type, exc, tb=None):
    """Сохранить отчёт, показать путь и предложить открыть Issue."""
    body = format_body(exc_type, exc, tb)
    path = write_report(body)
    title = issue_title(exc_type, exc)
    url = build_url(title, body)

    print("", file=sys.stderr)
    print(f"  непредвиденная ошибка: {_short(f'{exc_type.__name__}: {exc}', 300)}",
          file=sys.stderr)
    print(f"  отчёт: {path}", file=sys.stderr)
    if _can_prompt():
        _prompt(url, body)
    else:
        print("  отправить: " + url, file=sys.stderr)
    return url


def install():
    """Подключить перехват: основной поток и потоки threading."""
    global _installed
    if _installed or os.environ.get("RB_TUI_NO_CRASH_HOOK"):
        return
    _installed = True

    previous = sys.excepthook
    previous_thread = getattr(threading, "excepthook", None)

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, (SystemExit, KeyboardInterrupt, BrokenPipeError)):
            previous(exc_type, exc, tb)
            return
        try:
            handle(exc_type, exc, tb)
        except Exception:
            previous(exc_type, exc, tb)

    def thread_hook(args):
        if args.exc_type in (SystemExit, KeyboardInterrupt):
            if previous_thread:
                previous_thread(args)
            return
        try:
            handle(args.exc_type, args.exc_value, args.exc_traceback)
        except Exception:
            if previous_thread:
                previous_thread(args)

    sys.excepthook = hook
    if previous_thread is not None:
        threading.excepthook = thread_hook


# ── --report-bug ──

def _title_from_report(body):
    match = re.search(r"`([^`\n]{1,120})`", body)
    return _short(match.group(1), 120) if match else "Отчёт об ошибке rb-tui"


def send_report(path=None):
    """Открыть Issue с сохранённым отчётом. Возвращает ссылку."""
    path = path or last_report()
    if not path:
        raise FileNotFoundError("нет сохранённых отчётов об ошибках")
    with open(path, encoding="utf-8") as f:
        body = f.read()
    url = build_url(_title_from_report(body), body)
    if not open_issue(url):
        print("  браузер не открылся. Ссылка:")
        print("  " + url)
    return url