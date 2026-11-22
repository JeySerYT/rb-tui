"""Тесты самообновления: версии, имена файлов, sha256, распаковка."""

import hashlib
import io
import os
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

from rb_tui import update


class VersionTest(unittest.TestCase):
    def test_parse_plain_and_v_prefix(self):
        self.assertEqual(update._parse_version("1.2.3"), (1, 2, 3, ()))
        self.assertEqual(update._parse_version("v1.2.3"), (1, 2, 3, ()))

    def test_parse_prerelease(self):
        self.assertEqual(update._parse_version("0.5.0-beta.1"),
                         (0, 5, 0, ("beta", 1)))

    def test_parse_rejects_garbage(self):
        for value in ("", "abc", "1.2", "1.2.3.4"):
            with self.assertRaises(update.UpdateError):
                update._parse_version(value)

    def test_newer_patch_minor_major(self):
        self.assertTrue(update.is_newer("1.2.4", "1.2.3"))
        self.assertTrue(update.is_newer("1.3.0", "1.2.9"))
        self.assertTrue(update.is_newer("2.0.0", "1.9.9"))
        self.assertFalse(update.is_newer("1.2.3", "1.2.3"))

    def test_release_is_newer_than_prerelease(self):
        self.assertTrue(update.is_newer("1.0.0", "1.0.0-rc.1"))
        self.assertFalse(update.is_newer("1.0.0-rc.1", "1.0.0"))

    def test_prerelease_ordering(self):
        self.assertTrue(update.is_newer("1.0.0-beta.2", "1.0.0-beta.1"))
        self.assertTrue(update.is_newer("1.0.0-rc.1", "1.0.0-beta.9"))
        self.assertFalse(update.is_newer("1.0.0-beta.1", "1.0.0-beta.2"))

    def test_numeric_prerelease_sorts_before_text(self):
        # SemVer: 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta
        self.assertTrue(update.is_newer("1.0.0-alpha.1", "1.0.0-alpha"))
        self.assertTrue(update.is_newer("1.0.0-alpha.beta", "1.0.0-alpha.1"))


class AssetNameTest(unittest.TestCase):
    def test_linux_x86_64(self):
        self.assertEqual(update.asset_name("Linux", "x86_64"),
                         "rb-tui-linux-x86_64.tar.gz")

    def test_macos_arm64(self):
        self.assertEqual(update.asset_name("Darwin", "arm64"),
                         "rb-tui-darwin-arm64.tar.gz")

    def test_windows_amd64(self):
        self.assertEqual(update.asset_name("Windows", "AMD64"),
                         "rb-tui-windows-x86_64.zip")

    def test_unsupported(self):
        with self.assertRaises(update.UpdateError):
            update.asset_name("Plan9", "x86_64")
        with self.assertRaises(update.UpdateError):
            update.asset_name("Linux", "mips")


class Sha256Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "file.bin")
        with open(self.path, "wb") as f:
            f.write(b"rb-tui payload")

    def test_accepts_matching_checksum(self):
        digest = hashlib.sha256(b"rb-tui payload").hexdigest()
        update.verify_sha256(self.path, f"{digest}  file.bin\n", "file.bin")

    def test_rejects_mismatch(self):
        with self.assertRaises(update.UpdateError):
            update.verify_sha256(self.path, "0" * 64, "file.bin")

    def test_rejects_malformed_checksum(self):
        for text in ("", "not-a-hash", "abc"):
            with self.assertRaises(update.UpdateError):
                update.verify_sha256(self.path, text, "file.bin")


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _tar(self, name, payload=b"binary"):
        path = os.path.join(self.tmp.name, "a.tar.gz")
        with tarfile.open(path, "w:gz") as tf:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
        return path

    def test_extracts_tar(self):
        archive = self._tar("rb-tui", b"binary-data")
        dest = os.path.join(self.tmp.name, "out")
        update.extract_binary(archive, dest, "rb-tui-linux-x86_64.tar.gz")
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), b"binary-data")

    def test_extracts_tar_with_dot_prefix(self):
        archive = self._tar("./rb-tui", b"x")
        dest = os.path.join(self.tmp.name, "out")
        update.extract_binary(archive, dest, "rb-tui-linux-x86_64.tar.gz")
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), b"x")

    def test_rejects_tar_without_binary(self):
        archive = self._tar("install.sh", b"x")
        dest = os.path.join(self.tmp.name, "out")
        with self.assertRaises(update.UpdateError):
            update.extract_binary(archive, dest, "rb-tui-linux-x86_64.tar.gz")

    def test_extracts_zip(self):
        archive = os.path.join(self.tmp.name, "a.zip")
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("rb-tui.exe", b"pe-binary")
        dest = os.path.join(self.tmp.name, "out.exe")
        update.extract_binary(archive, dest, "rb-tui-windows-x86_64.zip")
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), b"pe-binary")


class FetchLatestTest(unittest.TestCase):
    """fetch_latest без сети: подменяем HTTP-ответ."""

    def _response(self, payload):
        class FakeResponse:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def read(self_inner):
                return payload.encode("utf-8") if isinstance(payload, str) else payload

        return FakeResponse()

    def test_requires_checksum_asset(self):
        import json
        body = json.dumps({
            "tag_name": "v1.0.0",
            "assets": [{
                "name": "rb-tui-linux-x86_64.tar.gz",
                "browser_download_url": "https://example.test/a.tar.gz",
            }],
        })
        with mock.patch.object(update, "asset_name",
                               return_value="rb-tui-linux-x86_64.tar.gz"), \
                mock.patch.object(update, "_request",
                                  return_value=self._response(body)):
            with self.assertRaises(update.UpdateError):
                update.fetch_latest()

    def test_returns_version_and_urls(self):
        import json
        body = json.dumps({
            "tag_name": "v1.0.0",
            "assets": [
                {"name": "rb-tui-linux-x86_64.tar.gz",
                 "browser_download_url": "https://example.test/a.tar.gz"},
                {"name": "rb-tui-linux-x86_64.tar.gz.sha256",
                 "browser_download_url": "https://example.test/a.sha256"},
            ],
        })
        with mock.patch.object(update, "asset_name",
                               return_value="rb-tui-linux-x86_64.tar.gz"), \
                mock.patch.object(update, "_request",
                                  return_value=self._response(body)):
            version, archive, checksum = update.fetch_latest()
        self.assertEqual(version, "v1.0.0")
        self.assertEqual(archive, "https://example.test/a.tar.gz")
        self.assertEqual(checksum, "https://example.test/a.sha256")


class FrozenTest(unittest.TestCase):
    def test_current_binary_requires_frozen(self):
        with mock.patch.object(update.sys, "frozen", False, create=True):
            with self.assertRaises(update.UpdateError):
                update.current_binary()

    def test_current_binary_returns_realpath_when_frozen(self):
        with mock.patch.object(update.sys, "frozen", True, create=True), \
                mock.patch.object(update.sys, "executable", "/opt/rb-tui"):
            self.assertEqual(update.current_binary(), os.path.realpath("/opt/rb-tui"))


if __name__ == "__main__":
    unittest.main()