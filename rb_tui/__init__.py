"""rb-tui: ReformBoss model catalog manager."""


def _read_version():
    try:
        from importlib.metadata import version, PackageNotFoundError

        try:
            return version("rb-tui")
        except PackageNotFoundError:
            pass
    except Exception:
        pass
    # фолбэк для запуска из исходников без установки
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    version_file = os.path.join(here, os.pardir, "VERSION")
    try:
        with open(version_file, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0-unknown"


__version__ = _read_version()