"""rb-tui: ReformBoss model catalog manager."""

import os
import re


def _read_version():
    # В исходниках VERSION — источник истины, даже если рядом лежит старый
    # egg-info от предыдущей сборки. В бинарнике VERSION лежит внутри пакета.
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(here, "VERSION"),
        os.path.join(here, os.pardir, "VERSION"),
    ):
        try:
            with open(candidate, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
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


def _ensure_ca_bundle():
    """Подставить системный CA-бандл, если OpenSSL ищет несуществующий путь.

    Бинарник, собранный на Ubuntu, ищет сертификаты в /usr/lib/ssl, которого
    нет на Arch/Fedora, и HTTPS падает с CERTIFICATE_VERIFY_FAILED.
    """
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import ssl

        cafile = ssl.get_default_verify_paths().cafile
        if cafile and os.path.isfile(cafile):
            return
    except Exception:
        pass
    for candidate in (
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
        "/etc/ssl/cert.pem",
        "/usr/local/etc/openssl/cert.pem",
    ):
        if os.path.isfile(candidate):
            os.environ["SSL_CERT_FILE"] = candidate
            return


_ensure_ca_bundle()