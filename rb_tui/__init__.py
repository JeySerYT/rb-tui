"""rb-tui: ReformBoss model catalog manager."""

import os
import re


def _read_version():
    # В исходниках VERSION — источник истины, даже если рядом лежит старый
    # egg-info от предыдущей сборки.
    here = os.path.dirname(os.path.abspath(__file__))
    version_file = os.path.join(here, os.pardir, "VERSION")
    try:
        with open(version_file, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        pass
    # Установленный пакет: версия из метаданных дистрибутива.
    try:
        from importlib.metadata import version, PackageNotFoundError

        try:
            return version("rb-tui")
        except PackageNotFoundError:
            pass
    except Exception:
        pass
    return "0.0.0-unknown"


def _pretty_version(value):
    """PEP 440 -> привычная запись: 0.2.0b2 -> 0.2.0-beta.2."""
    m = re.fullmatch(r"(\d+(?:\.\d+)*)(a|b|rc)(\d+)", value or "")
    if not m:
        return value
    base, tag, num = m.groups()
    name = {"a": "alpha", "b": "beta", "rc": "rc"}[tag]
    return f"{base}-{name}.{num}"


__version__ = _pretty_version(_read_version())