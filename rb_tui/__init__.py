"""rb-tui: ReformBoss model catalog manager."""

import os


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


__version__ = _read_version()