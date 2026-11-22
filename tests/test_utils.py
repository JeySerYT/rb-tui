"""Тесты утилит: выбор без fzf, бэкапы, атомарная запись."""

import os
import tempfile
import unittest
from unittest import mock

from rb_tui import utils


class SelectionTest(unittest.TestCase):
    def test_list_of_numbers(self):
        self.assertEqual(utils.parse_selection("1,3", 4), [0, 2])

    def test_range(self):
        self.assertEqual(utils.parse_selection("2-4", 5), [1, 2, 3])

    def test_reverse_range_is_tolerated(self):
        self.assertEqual(utils.parse_selection("4-2", 5), [1, 2, 3])

    def test_all(self):
        self.assertEqual(utils.parse_selection("all", 3), [0, 1, 2])
        self.assertEqual(utils.parse_selection("все", 2), [0, 1])

    def test_empty_and_garbage(self):
        self.assertEqual(utils.parse_selection("", 3), [])
        self.assertEqual(utils.parse_selection("abc", 3), [])
        self.assertEqual(utils.parse_selection("0,9", 3), [])

    def test_no_duplicates(self):
        self.assertEqual(utils.parse_selection("1,1,1-2", 3), [0, 1])


class FzfFallbackTest(unittest.TestCase):
    def test_non_interactive_without_fzf_returns_empty(self):
        fake_stdin = mock.Mock(isatty=lambda: False)
        with mock.patch.object(utils.shutil, "which", return_value=None), \
                mock.patch.object(utils.sys, "stdin", fake_stdin), \
                mock.patch.object(utils, "print"):
            self.assertEqual(utils.fzf_multi(["a", "b"], "h", "p> "), [])

    def test_numbered_pick_reads_numbers(self):
        fake_stdin = mock.Mock(isatty=lambda: True)
        with mock.patch.object(utils.shutil, "which", return_value=None), \
                mock.patch.object(utils.sys, "stdin", fake_stdin), \
                mock.patch("builtins.input", return_value="2"), \
                mock.patch.object(utils, "print"):
            self.assertEqual(
                utils.fzf_multi(["alpha", "beta"], "h", "p> "), ["beta"],
            )


class BackupNameTest(unittest.TestCase):
    def test_prefix_follows_config_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "opencode.jsonc")
            with mock.patch.object(utils, "CONFIG", path):
                self.assertEqual(utils.backup_prefix(), "opencode.jsonc.bak-")

    def test_prune_sees_jsonc_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = os.path.join(tmp, "opencode.jsonc")
            old = os.path.join(tmp, "opencode.jsonc.bak-20200101-000000")
            fresh = os.path.join(tmp, "opencode.jsonc.bak-20990101-000000")
            for path in (old, fresh):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("{}")
            os.utime(old, (0, 0))
            with mock.patch.object(utils, "CONFIG", config), \
                    mock.patch.object(utils, "print"):
                removed = utils.prune_backups(days=30)
            self.assertEqual(removed, 1)
            self.assertTrue(os.path.exists(fresh))


class AtomicWriteTest(unittest.TestCase):
    def test_retries_busy_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "file.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("old")
            real_replace = os.replace
            calls = []

            def flaky(src, dst):
                calls.append(dst)
                if len(calls) < 3:
                    raise PermissionError("busy")
                return real_replace(src, dst)

            with mock.patch.object(utils.os, "replace", flaky), \
                    mock.patch.object(utils.time, "sleep", lambda *_: None):
                utils.atomic_write(path, "new")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "new")

    def test_busy_target_eventually_raises_readable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "file.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("old")
            with mock.patch.object(
                    utils.os, "replace", side_effect=PermissionError("busy")), \
                    mock.patch.object(utils.time, "sleep", lambda *_: None):
                with self.assertRaises(OSError) as ctx:
                    utils.atomic_write(path, "new")
            self.assertIn("занят", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()