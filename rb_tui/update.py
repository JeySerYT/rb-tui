"""Самообновление standalone-бинарника из GitHub Releases.

Работает только для бинарника, собранного PyInstaller: при запуске из
исходников обновлять нечего. Скачивает архив под текущую платформу,
проверяет sha256 из релиза и атомарно заменяет исполняемый файл.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

from rb_tui import __version__

DEFAULT_REPO = "JeySerYT/rb-tui"
USER_AGENT = f"rb-tui/{__version__}"
TIMEOUT = 60
DEFAULT_CHECK_TTL = 3600
CHECK_TIMEOUT = 3


class UpdateError(Exception):
    """Обновление невозможно; сообщение предназначено пользователю."""


def repo():
    return os.environ.get("RB_TUI_REPO", DEFAULT_REPO)


def asset_name(system=None, machine=None):
    """Имя релизного архива под текущую ОС и архитектуру."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()

    os_name = {
        "linux": "linux",
        "darwin": "darwin",
        "windows": "windows",
    }.get(system)
    if not os_name:
        raise UpdateError(f"неподдерживаемая ОС: {system}")

    arch = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine)
    if not arch:
        raise UpdateError(f"неподдерживаемая архитектура: {machine}")

    ext = "zip" if os_name == "windows" else "tar.gz"
    return f"rb-tui-{os_name}-{arch}.{ext}"


def _parse_version(value):
    """SemVer в кортеж для сравнения: (major, minor, patch, prerelease)."""
    value = (value or "").strip()
    if value.startswith("v"):
        value = value[1:]
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", value)
    if not m:
        raise UpdateError(f"непонятная версия: {value or 'пусто'}")
    major, minor, patch, pre = m.groups()
    pre_parts = ()
    if pre:
        pre_parts = tuple(
            int(p) if p.isdigit() else p for p in pre.split(".")
        )
    return int(major), int(minor), int(patch), pre_parts


def is_newer(latest, current):
    """True, если latest новее current. Релиз выше pre-release."""
    left = _parse_version(latest)
    right = _parse_version(current)
    if left[:3] != right[:3]:
        return left[:3] > right[:3]
    if not left[3]:
        return bool(right[3])
    if not right[3]:
        return False
    # Кортежи из int/str в Python 3 нельзя сравнивать напрямую.
    for a, b in zip(left[3], right[3]):
        if a == b:
            continue
        if isinstance(a, int) and isinstance(b, int):
            return a > b
        if isinstance(a, int):
            return False
        if isinstance(b, int):
            return True
        return a > b
    return len(left[3]) > len(right[3])


def _request(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_latest(timeout=TIMEOUT):
    """Вернуть (версия, url_архива, url_sha256) последнего релиза."""
    url = f"https://api.github.com/repos/{repo()}/releases/latest"
    try:
        with _request(url, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError(
                f"у {repo()} нет опубликованных релизов. "
                "Установщик: curl -fsSL .../install.sh | sh"
            )
        raise UpdateError(f"GitHub API ответил HTTP {e.code}")
    except Exception as e:
        raise UpdateError(f"не удалось проверить обновления: {e}")

    version = data.get("tag_name") or ""
    assets = {a.get("name"): a.get("browser_download_url")
              for a in data.get("assets") or []}
    name = asset_name()
    if name not in assets:
        raise UpdateError(f"в релизе {version} нет файла {name}")
    checksum = assets.get(name + ".sha256")
    if not checksum:
        raise UpdateError(
            f"в релизе {version} нет {name}.sha256 — обновление отменено"
        )
    return version, assets[name], checksum


def _cache_path():
    from rb_tui.utils import CACHE

    return os.path.join(CACHE, "update-check.json")


def _read_cache(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(path, payload):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".update-check-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _ttl():
    raw = os.environ.get("RB_TUI_UPDATE_TTL", "")
    if not raw:
        return DEFAULT_CHECK_TTL
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_CHECK_TTL


def check_cached(ttl=None, timeout=CHECK_TIMEOUT):
    """Проверить обновление с кешем. None — обновлений нет или сеть недоступна.

    Результат живёт TTL (по умолчанию час), чтобы не упираться в лимит
    GitHub API при частых запусках. RB_TUI_UPDATE_TTL=0 проверяет каждый раз,
    RB_TUI_NO_UPDATE_CHECK=1 отключает проверку полностью.
    """
    if os.environ.get("RB_TUI_NO_UPDATE_CHECK"):
        return None
    ttl = _ttl() if ttl is None else ttl
    path = _cache_path()
    data = _read_cache(path)
    checked_at = data.get("checked_at")
    fresh = (
        isinstance(checked_at, (int, float))
        and time.time() - checked_at < ttl
        and data.get("current") == __version__
    )
    if fresh:
        return data.get("latest") if data.get("newer") else None
    try:
        latest, _, _ = fetch_latest(timeout=timeout)
    except UpdateError:
        return None
    latest_clean = latest.lstrip("v")
    newer = is_newer(latest, __version__)
    _save_cache(path, {
        "checked_at": time.time(),
        "current": __version__,
        "latest": latest_clean,
        "newer": newer,
    })
    return latest_clean if newer else None


def download(url, dest):
    """Скачать url в dest, вернуть количество байт."""
    try:
        with _request(url) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
    except Exception as e:
        raise UpdateError(f"не удалось скачать {url}: {e}")
    return os.path.getsize(dest)


def verify_sha256(archive, checksum_text, asset):
    """Проверить архив по содержимому .sha256 из релиза."""
    first = (checksum_text or "").strip().split()[0] if checksum_text.strip() else ""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", first or ""):
        raise UpdateError("файл контрольной суммы повреждён")
    digest = hashlib.sha256()
    with open(archive, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != first.lower():
        raise UpdateError(f"контрольная сумма не совпала для {asset}")


def extract_binary(archive, dest, asset=None):
    """Достать исполняемый файл из tar.gz или zip, не распаковывая всё."""
    asset = asset or archive
    if str(asset).endswith(".zip"):
        member = "rb-tui.exe"
        try:
            with zipfile.ZipFile(archive) as zf, zf.open(member) as src, \
                    open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
        except (KeyError, zipfile.BadZipFile) as e:
            raise UpdateError(f"в архиве нет {member}: {e}")
        return dest

    try:
        with tarfile.open(archive, "r:gz") as tf:
            members = [
                m for m in tf.getmembers()
                if m.name in ("rb-tui", "./rb-tui") and m.isfile()
            ]
            if len(members) != 1:
                raise UpdateError("в архиве нет ровно одного файла rb-tui")
            src = tf.extractfile(members[0])
            if src is None:
                raise UpdateError("не удалось прочитать rb-tui из архива")
            with src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    except tarfile.TarError as e:
        raise UpdateError(f"архив повреждён: {e}")
    return dest


def current_binary():
    """Путь к исполняемому файлу, если это standalone-бинарник."""
    if not getattr(sys, "frozen", False):
        raise UpdateError(
            "это запуск из исходников — обновлять нечего. "
            "Для standalone-версии используй установленный rb-tui."
        )
    return os.path.realpath(sys.executable)


def _schedule_windows_replace(staged, target):
    """Заменить файл после выхода процесса: Windows не даёт перезаписать exe."""
    script = os.path.join(
        tempfile.gettempdir(), f"rb-tui-update-{os.getpid()}.cmd",
    )
    lines = [
        "@echo off",
        'set "src=%~1"',
        'set "dst=%~2"',
        "set /a tries=0",
        "ping -n 3 127.0.0.1 >nul",
        ":retry",
        'move /Y "%src%" "%dst%" >nul 2>&1',
        "if not errorlevel 1 goto done",
        "set /a tries+=1",
        "if %tries% geq 30 goto done",
        "ping -n 2 127.0.0.1 >nul",
        "goto retry",
        ":done",
        'del "%~f0" >nul 2>&1',
    ]
    with open(script, "w", encoding="ascii", newline="\r\n") as f:
        f.write("\n".join(lines))

    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            ["cmd", "/c", script, staged, target],
            creationflags=flags, close_fds=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        raise UpdateError(f"не удалось запустить замену файла: {e}")


def _install(temp_binary, target):
    """Заменить target на temp_binary, сохранив права и проверив запуск."""
    directory = os.path.dirname(target) or "."
    fd, staged = tempfile.mkstemp(prefix=".rb-tui-new-", dir=directory)
    os.close(fd)
    keep_staged = False
    try:
        shutil.copyfile(temp_binary, staged)
        os.chmod(staged, 0o755)
        try:
            check = subprocess.run(
                [staged, "--version"], capture_output=True, text=True, timeout=20,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise UpdateError(f"новый бинарник не запускается: {e}")
        if check.returncode != 0:
            raise UpdateError(
                f"новый бинарник завершился с кодом {check.returncode}: "
                f"{(check.stderr or check.stdout).strip()[:200]}"
            )
        if sys.platform.startswith("win"):
            _schedule_windows_replace(staged, target)
            keep_staged = True
        else:
            try:
                os.replace(staged, target)
            except OSError as e:
                raise UpdateError(
                    f"не удалось заменить {target}: {e}. "
                    "Проверь права на каталог."
                )
    finally:
        if not keep_staged and os.path.exists(staged):
            try:
                os.unlink(staged)
            except OSError:
                pass


def check():
    """Проверить наличие новой версии. Возвращает (current, latest, newer)."""
    latest, _, _ = fetch_latest()
    return __version__, latest.lstrip("v"), is_newer(latest, __version__)


def update(force=False, progress=print):
    """Скачать и установить последнюю версию. Возвращает новую версию."""
    latest, archive_url, checksum_url = fetch_latest()
    latest_clean = latest.lstrip("v")
    if not force and not is_newer(latest, __version__):
        progress(f"  уже последняя версия: v{__version__}")
        return __version__

    target = current_binary()
    name = asset_name()
    progress(f"  текущая: v{__version__} · новая: v{latest_clean}")
    progress(f"  скачиваю {name}...")

    with tempfile.TemporaryDirectory(prefix="rb-tui-update-") as tmp:
        archive = os.path.join(tmp, name)
        checksum = os.path.join(tmp, name + ".sha256")
        download(archive_url, archive)
        download(checksum_url, checksum)
        with open(checksum, encoding="utf-8") as f:
            verify_sha256(archive, f.read(), name)
        progress("  контрольная сумма ok")
        binary = extract_binary(archive, os.path.join(tmp, "rb-tui"), name)
        _install(binary, target)

    if sys.platform.startswith("win"):
        progress(f"  v{latest_clean} заменит файл после выхода (пара секунд)")
    else:
        progress(f"  обновлено: v{__version__} → v{latest_clean}")
    progress(f"  файл: {target}")
    return latest_clean