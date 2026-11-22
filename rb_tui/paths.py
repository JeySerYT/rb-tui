"""Пути OpenCode и rb-tui на разных ОС.

OpenCode ищет глобальный конфиг в платформенном каталоге: `%APPDATA%\\opencode`
на Windows, `~/Library/Application Support/opencode` на macOS и
`$XDG_CONFIG_HOME/opencode` на Linux. Дополнительно он читает старый
`~/.config/opencode` и машинный каталог (`%ProgramData%`, `/etc/opencode`,
`/Library/Application Support/opencode`).

В одном каталоге могут лежать `opencode.json` и `opencode.jsonc`; второй
загружается позже и потому важнее. Раньше rb-tui знал только жёстко
зашитый `~/.config/opencode/opencode.json`, из-за чего на Windows и macOS
не находил конфиг вообще.
"""

import os
import sys

APP = "opencode"
CACHE_NAME = "reformboss-tui"
WINDOWS_CACHE_NAME = "rb-tui"
# .jsonc importantнее .json: OpenCode загружает его вторым.
CONFIG_NAMES = ("opencode.jsonc", "opencode.json")
PROVIDER = "reformboss"


def platform_name(system=None):
    """Свести sys.platform / platform.system() к linux|darwin|windows."""
    value = (system or sys.platform or "").lower()
    if value.startswith("win"):
        return "windows"
    if value.startswith("darwin") or value == "macos":
        return "darwin"
    return "linux"


def _home(home=None):
    return os.path.expanduser("~") if home is None else home


def _expand(path, home):
    path = os.path.expandvars(path)
    if path == "~":
        return home
    if path.startswith("~/") or path.startswith("~\\"):
        return os.path.join(home, path[2:])
    if path.startswith("~"):
        return os.path.expanduser(path)
    return path


def config_dirs(system=None, env=None, home=None):
    """Каталоги глобального конфига OpenCode в порядке приоритета.

    Сначала пользовательские (туда можно писать), затем машинные (только
    чтение). Значение `OPENCODE_CONFIG_DIR` перекрывает платформенный путь.
    """
    env = os.environ if env is None else env
    home = _home(home)
    plat = platform_name(system)

    dirs = []
    explicit = (env.get("OPENCODE_CONFIG_DIR") or "").strip()
    if explicit:
        dirs.append(_expand(explicit, home))

    if plat == "windows":
        appdata = (env.get("APPDATA") or "").strip()
        if not appdata:
            appdata = os.path.join(home, "AppData", "Roaming")
        dirs.append(os.path.join(appdata, APP))
        dirs.append(os.path.join(home, ".config", APP))
        programdata = (env.get("ProgramData") or env.get("PROGRAMDATA") or "").strip()
        if programdata:
            dirs.append(os.path.join(programdata, APP))
    elif plat == "darwin":
        dirs.append(os.path.join(home, "Library", "Application Support", APP))
        dirs.append(os.path.join(home, ".config", APP))
        dirs.append(os.path.join("/Library", "Application Support", APP))
    else:
        xdg = (env.get("XDG_CONFIG_HOME") or "").strip()
        dirs.append(os.path.join(_expand(xdg, home) if xdg else os.path.join(home, ".config"), APP))
        dirs.append(os.path.join(home, ".config", APP))
        dirs.append(os.path.join("/etc", APP))

    seen, unique = set(), []
    for path in dirs:
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def candidate_files(system=None, env=None, home=None):
    """Все пути, где может лежать конфиг, в порядке приоритета."""
    return [
        os.path.join(directory, name)
        for directory in config_dirs(system, env, home)
        for name in CONFIG_NAMES
    ]


def _mentions_provider(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f'"{PROVIDER}"' in f.read()
    except OSError:
        return False


def discover_config(system=None, env=None, home=None):
    """Путь к конфигу, который использует OpenCode.

    Явный `RB_TUI_CONFIG` важнее всего. Иначе берём первый существующий файл,
    но если провайдер reformboss нашёлся в другом — предпочитаем его: иначе
    правки уйдут в пустой или чужой конфиг, который перекрывает нужный.
    """
    env = os.environ if env is None else env
    home = _home(home)
    explicit = (env.get("RB_TUI_CONFIG") or "").strip()
    if explicit:
        return _expand(explicit, home)

    files = candidate_files(system, env, home)
    existing = [path for path in files if os.path.isfile(path)]
    for path in existing:
        if _mentions_provider(path):
            return path
    if existing:
        return existing[0]
    # Конфига нет: подсказываем привычное имя в приоритетном каталоге.
    return os.path.join(config_dirs(system, env, home)[0], "opencode.json")


def searched_paths(system=None, env=None, home=None):
    """Что показать пользователю, если конфиг не найден."""
    explicit = ((os.environ if env is None else env).get("RB_TUI_CONFIG") or "").strip()
    if explicit:
        return [_expand(explicit, _home(home))]
    return candidate_files(system, env, home)


def cache_dir(system=None, env=None, home=None):
    """Каталог кеша rb-tui: на Windows — LOCALAPPDATA, иначе прежний XDG-путь.

    XDG-путь на Linux и macOS не меняем, чтобы не потерять накопленные метрики.
    """
    env = os.environ if env is None else env
    home = _home(home)
    if platform_name(system) == "windows":
        base = (env.get("LOCALAPPDATA") or "").strip()
        if not base:
            base = os.path.join(home, "AppData", "Local")
        return os.path.join(base, WINDOWS_CACHE_NAME)
    base = (env.get("XDG_CONFIG_HOME") or "").strip()
    if base:
        base = _expand(base, home)
    else:
        base = os.path.join(home, ".config")
    return os.path.join(base, CACHE_NAME)


def set_config_path(path):
    """Переопределить конфиг на время запуска (--config / RB_TUI_CONFIG).

    CONFIG импортируется по значению в несколько модулей, поэтому обновляем
    его везде, где он уже загружен.
    """
    resolved = os.path.abspath(_expand(path, _home()))
    from rb_tui import utils

    utils.CONFIG = resolved
    for name in ("rb_tui.config", "rb_tui.sync", "rb_tui.cli"):
        module = sys.modules.get(name)
        if module is not None:
            module.CONFIG = resolved
    return resolved