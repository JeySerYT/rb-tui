"""Кроссплатформенная консоль: UTF-8, ANSI и пауза перед закрытием окна."""

import os
import sys

# ENABLE_VIRTUAL_TERMINAL_PROCESSING
_VT_FLAG = 0x0004
_STD_HANDLES = (-11, -12)  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE


def _reconfigure(stream):
    """Перевести поток в UTF-8, чтобы эмодзи не падали на cp1251/cp866."""
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return False
    try:
        reconfigure(encoding="utf-8", errors="replace")
        return True
    except (AttributeError, OSError, ValueError):
        return False


def enable_ansi():
    """Включить VT-последовательности в консоли Windows. Best-effort."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ok = False
        for handle_id in _STD_HANDLES:
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                continue
            if kernel32.SetConsoleMode(handle, mode.value | _VT_FLAG):
                ok = True
        return ok
    except Exception:
        return False


def setup():
    """Подготовить потоки. Вызывается один раз при импорте utils.

    Возвращает True, если цветной вывод поддерживается на этой платформе.
    """
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        _reconfigure(stream)
    if os.name == "nt":
        return enable_ansi()
    return True


def can_color(stream=None):
    stream = stream or sys.stdout
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def wait_before_exit(message="\nНажми Enter, чтобы закрыть окно..."):
    """Не дать окну консоли закрыться сразу после ошибки.

    Актуально для Windows, где бинарник запускают двойным кликом. В пайпах,
    CI и OpenCode stdin не терминал — ничего не спрашиваем.
    """
    if os.name != "nt":
        return
    if os.environ.get("RB_TUI_NO_PAUSE"):
        return
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return
        input(message)
    except (EOFError, KeyboardInterrupt):
        pass