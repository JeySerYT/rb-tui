"""Тесты JSONC-конфига: правки только reformboss, атомарность, проверки."""

import json
import os
import stat
import tempfile
import unittest
from unittest import mock

from rb_tui import config, utils

BASE = """{
  // чужой провайдер стоит первым — его трогать нельзя
  "providers": {
    "other": {
      "models": {
        "wrong-model": { "name": "Wrong" }
      }
    },
    "reformboss": {
      "settings": {
        "baseURL": "https://api.reformboss.com/v1",
        "apiKey": "{file:%s}"
      },
      "models": {
        "alpha": { "name": "Alpha" }, // комментарий
        "beta": { "name": "Beta" },
      }
    }
  }
}
"""


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "opencode.json")
        self.key = os.path.join(self.tmp.name, "key.txt")
        with open(self.key, "w", encoding="utf-8") as f:
            f.write("secret\n")
        os.chmod(self.key, 0o600)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(BASE % self.key)
        for patcher in (
            mock.patch.object(config, "CONFIG", self.path),
            mock.patch.object(utils, "CONFIG", self.path),
            mock.patch.object(config, "STATE", os.path.join(self.tmp.name, "state.json")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def parsed(self):
        return json.loads(utils.strip_jsonc(self.read()))

    def test_models_span_points_to_reformboss(self):
        span = config.find_models_span(self.read())
        self.assertIsNotNone(span)
        start, end = span
        block = self.read()[start:end]
        self.assertIn('"alpha"', block)
        self.assertNotIn("wrong-model", block)

    def test_apply_edits_adds_only_to_reformboss(self):
        ok, msg = config.apply_edits(["gamma"], [], [], "22.11.2026")
        self.assertTrue(ok, msg)
        data = self.parsed()
        self.assertIn("gamma", data["providers"]["reformboss"]["models"])
        self.assertEqual(
            list(data["providers"]["other"]["models"]), ["wrong-model"],
        )

    def test_apply_edits_comments_out_and_keeps_json_valid(self):
        ok, msg = config.apply_edits([], ["beta"], [], "22.11.2026")
        self.assertTrue(ok, msg)
        raw = self.read()
        self.assertIn("// \"beta\"", raw)
        self.assertTrue(utils.parse_ok(raw))
        _, _, models = config.load_config()
        self.assertNotIn("beta", models)

    def test_apply_edits_deletes_without_breaking_comma(self):
        ok, msg = config.apply_edits([], [], ["beta"], "22.11.2026")
        self.assertTrue(ok, msg)
        self.assertTrue(utils.parse_ok(self.read()))
        _, _, models = config.load_config()
        self.assertNotIn("beta", models)

    def test_noop_edit_reports_nothing_to_do(self):
        ok, msg = config.apply_edits([], [], [], "22.11.2026")
        self.assertFalse(ok)
        self.assertIn("нечего", msg)

    def test_config_check_flags_missing_key_file(self):
        os.unlink(self.key)
        issues = config.config_check()
        self.assertTrue(any("не найден" in i for i in issues))

    @unittest.skipUnless(os.name == "posix", "биты прав есть только на POSIX")
    def test_config_check_flags_insecure_key_permissions(self):
        os.chmod(self.key, 0o644)
        issues = config.config_check()
        self.assertTrue(any("chmod 600" in i for i in issues))

    def test_config_check_flags_bad_base_url_and_empty_name(self):
        broken = (BASE % self.key).replace(
            "https://api.reformboss.com/v1", "reformboss",
        ).replace('"name": "Alpha"', '"name": ""')
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(broken)
        issues = config.config_check()
        self.assertTrue(any("baseURL" in i for i in issues))
        self.assertTrue(any("пустым name" in i for i in issues))

    @unittest.skipUnless(os.name == "posix", "биты прав есть только на POSIX")
    def test_apply_edits_restores_readable_permissions(self):
        config.apply_edits(["gamma"], [], [], "22.11.2026")
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        # atomic_write не должен оставлять файл без прав владельца
        self.assertTrue(mode & stat.S_IRUSR)


if __name__ == "__main__":
    unittest.main()