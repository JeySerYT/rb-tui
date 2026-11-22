"""Тесты автосинхронизации, кэша каталога и rollback."""

import json
import os
import tempfile
import unittest
from unittest import mock

from rb_tui import sync, utils


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, "catalog-state.json")
        self.missing = os.path.join(self.tmp.name, "missing.json")
        self.log = os.path.join(self.tmp.name, "auto-sync.log")
        for patcher in (
            mock.patch.object(sync, "STATE", self.state),
            mock.patch.object(sync, "MISSING", self.missing),
            mock.patch.object(sync, "LOG", self.log),
            mock.patch.object(sync, "apply_edits", return_value=(True, "bak")),
            mock.patch.object(sync, "log_auto"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_catalog_roundtrip_keeps_owners(self):
        sync.save_catalog(["a", "b"], {"a": "deepseek"})
        date, models = sync.load_prev_catalog()
        self.assertEqual(models, ["a", "b"])
        self.assertIsNotNone(date)
        self.assertEqual(sync.load_catalog_owned(), {"a": "deepseek"})

    def test_new_models_are_added(self):
        sync.auto_sync(["new"], [], ["new"])
        sync.apply_edits.assert_called_once()
        kwargs = sync.apply_edits.call_args.kwargs
        self.assertEqual(kwargs["adds"], ["new"])

    def test_missing_models_pruned_after_threshold(self):
        with mock.patch.dict(os.environ, {"REFORMBOSS_PRUNE_AFTER": "2"}):
            sync.auto_sync([], ["gone"], ["alive"])
            self.assertFalse(sync.apply_edits.called)
            sync.auto_sync([], ["gone"], ["alive"])

        kwargs = sync.apply_edits.call_args.kwargs
        self.assertEqual(kwargs["comment_out"], ["gone"])
        with open(self.missing, encoding="utf-8") as f:
            self.assertNotIn("gone", json.load(f))

    def test_rollback_restores_last_valid_backup(self):
        config_path = os.path.join(self.tmp.name, "opencode.json")
        backup = config_path + ".bak-20260101-000000"
        with open(backup, "w", encoding="utf-8") as f:
            f.write('{"providers": {"reformboss": {}}}')
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("{broken")
        with mock.patch.object(utils, "CONFIG", config_path), \
                mock.patch.object(sync, "backup_config", return_value="bak"):
            ok, name = sync.auto_rollback()
        self.assertTrue(ok)
        self.assertEqual(name, os.path.basename(backup))
        with open(config_path, encoding="utf-8") as f:
            self.assertIn("reformboss", f.read())

    def test_rollback_without_backups(self):
        with mock.patch.object(utils, "CONFIG", os.path.join(self.tmp.name, "none.json")):
            ok, msg = sync.auto_rollback()
        self.assertFalse(ok)
        self.assertIn("нет", msg)


if __name__ == "__main__":
    unittest.main()