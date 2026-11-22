"""Тесты самообновления: версии, имена файлов, sha256, распаковка."""

import hashlib
import io
import json
import os
import tarfile
import tempfile
import time
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


class WindowsReplaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_schedule_writes_move_script_and_launches_it(self):
        staged = os.path.join(self.tmp.name, ".rb-tui-new-x")
        target = os.path.join(self.tmp.name, "rb-tui.exe")
        with mock.patch.object(update.tempfile, "gettempdir",
                               return_value=self.tmp.name), \
                mock.patch.object(update.subprocess, "Popen") as popen:
            update._schedule_windows_replace(staged, target)
        script = os.path.join(self.tmp.name,
                              f"rb-tui-update-{os.getpid()}.cmd")
        with open(script, encoding="ascii") as f:
            body = f.read()
        self.assertIn('move /Y "%src%" "%dst%"', body)
        self.assertIn(":retry", body)
        popen.assert_called_once()
        self.assertEqual(popen.call_args[0][0][-2:], [staged, target])

    def test_install_uses_helper_on_windows(self):
        target = os.path.join(self.tmp.name, "rb-tui.exe")
        with open(target, "wb") as f:
            f.write(b"old")
        temp_binary = os.path.join(self.tmp.name, "download")
        with open(temp_binary, "wb") as f:
            f.write(b"new")

        run_result = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(update.sys, "platform", "win32"), \
                mock.patch.object(update.subprocess, "run",
                                  return_value=run_result), \
                mock.patch.object(update, "_schedule_windows_replace") as helper, \
                mock.patch.object(update.os, "replace") as replace:
            update._install(temp_binary, target)

        helper.assert_called_once()
        replace.assert_not_called()
        staged = helper.call_args[0][0]
        self.addCleanup(lambda: os.path.exists(staged) and os.unlink(staged))
        self.assertTrue(os.path.exists(staged))
        with open(target, "rb") as f:
            self.assertEqual(f.read(), b"old")


class CheckCachedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "update-check.json")
        patcher = mock.patch.object(update, "_cache_path", return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("RB_TUI_NO_UPDATE_CHECK", None)
        os.environ.pop("RB_TUI_UPDATE_TTL", None)

    def _write(self, **payload):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def _cache(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_disabled_by_env(self):
        os.environ["RB_TUI_NO_UPDATE_CHECK"] = "1"
        with mock.patch.object(update, "fetch_latest") as fetch:
            self.assertIsNone(update.check_cached())
        fetch.assert_not_called()

    def test_fresh_cache_returns_newer_without_network(self):
        self._write(checked_at=time.time(), current=update.__version__,
                    latest="9.9.9", newer=True)
        with mock.patch.object(update, "fetch_latest") as fetch:
            self.assertEqual(update.check_cached(), "9.9.9")
        fetch.assert_not_called()

    def test_fresh_cache_without_update_returns_none(self):
        self._write(checked_at=time.time(), current=update.__version__,
                    latest=update.__version__, newer=False)
        with mock.patch.object(update, "fetch_latest") as fetch:
            self.assertIsNone(update.check_cached())
        fetch.assert_not_called()

    def test_stale_cache_refetches_and_saves(self):
        self._write(checked_at=time.time() - 7200,
                    current=update.__version__, latest="0.0.1", newer=False)
        with mock.patch.object(update, "fetch_latest",
                               return_value=("v9.9.9", "a", "b")):
            self.assertEqual(update.check_cached(), "9.9.9")
        saved = self._cache()
        self.assertTrue(saved["newer"])
        self.assertEqual(saved["latest"], "9.9.9")
        self.assertEqual(saved["current"], update.__version__)

    def test_cache_from_other_version_is_ignored(self):
        self._write(checked_at=time.time(), current="0.0.1",
                    latest="9.9.9", newer=True)
        with mock.patch.object(update, "fetch_latest",
                               return_value=(update.__version__, "a", "b")):
            self.assertIsNone(update.check_cached())
        self.assertFalse(self._cache()["newer"])

    def test_ttl_zero_always_refetches(self):
        self._write(checked_at=time.time(), current=update.__version__,
                    latest="9.9.9", newer=True)
        with mock.patch.object(update, "fetch_latest",
                               return_value=("v9.9.9", "a", "b")) as fetch:
            self.assertEqual(update.check_cached(ttl=0), "9.9.9")
        fetch.assert_called_once()

    def test_network_error_returns_none_and_keeps_cache(self):
        self._write(checked_at=time.time() - 7200,
                    current=update.__version__, latest="1.0.0", newer=False)
        with mock.patch.object(update, "fetch_latest",
                               side_effect=update.UpdateError("offline")):
            self.assertIsNone(update.check_cached())
        self.assertEqual(self._cache()["latest"], "1.0.0")


class NotifyTest(unittest.TestCase):
    def test_frozen_binary_prints_notice(self):
        from rb_tui import cli

        buf = io.StringIO()
        with mock.patch.object(cli.sys, "frozen", True, create=True), \
                mock.patch("rb_tui.update.check_cached", return_value="9.9.9"), \
                mock.patch("sys.stdout", buf):
            cli.notify_update_available()
        out = buf.getvalue()
        self.assertIn("9.9.9", out)
        self.assertIn("--update", out)

    def test_source_run_is_silent(self):
        from rb_tui import cli

        buf = io.StringIO()
        with mock.patch.object(cli.sys, "frozen", False, create=True), \
                mock.patch("rb_tui.update.check_cached") as check, \
                mock.patch("sys.stdout", buf):
            cli.notify_update_available()
        check.assert_not_called()
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()