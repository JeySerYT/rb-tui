"""Тесты экспорта метрик в JSON, CSV и HTML."""

import json
import os
import tempfile
import unittest
from unittest import mock

from rb_tui import export

SAMPLE = {
    "model-x": [
        {"ts": "2026-01-01 00:00", "status": "OK", "ttft": 1.0,
         "total_time": 1.0, "tokens": 3},
        {"ts": "2026-01-01 01:00", "status": "OK", "ttft": 2.0,
         "total_time": 2.0, "tokens": 4},
        {"ts": "2026-01-01 02:00", "status": "OK", "ttft": 1.5,
         "total_time": 1.5, "tokens": 3},
    ],
}


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(export, "load_metrics", return_value=SAMPLE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_json_to_stdout(self):
        data = json.loads(export.export_json())
        self.assertEqual(data["total_models"], 1)
        self.assertEqual(data["models"]["model-x"]["status"], "stable")

    def test_json_to_file(self):
        path = os.path.join(self.tmp.name, "out.json")
        self.assertEqual(export.export_json(path), path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("model-x", data["models"])

    def test_csv_to_stdout(self):
        text = export.export_csv()
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("model,status"))
        self.assertIn("model-x", lines[1])

    def test_csv_to_file(self):
        path = os.path.join(self.tmp.name, "out.csv")
        self.assertEqual(export.export_csv(path), path)
        with open(path, encoding="utf-8") as f:
            self.assertIn("model-x", f.read())

    def test_html_to_stdout(self):
        html = export.export_html()
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("model-x", html)

    def test_html_escapes_model_id(self):
        evil = "<img src=x onerror=alert(1)>"
        with mock.patch.object(export, "load_metrics",
                               return_value={evil: SAMPLE["model-x"]}):
            html = export.export_html()
        self.assertNotIn(evil, html)
        self.assertIn("&lt;img", html)

    def test_csv_quotes_commas(self):
        mid = "vendor,model"
        with mock.patch.object(export, "load_metrics",
                               return_value={mid: SAMPLE["model-x"]}):
            text = export.export_csv()
        self.assertIn('"vendor,model"', text.splitlines()[1])

    def test_csv_neutralizes_formula_prefix(self):
        mid = "=HYPERLINK(1)"
        with mock.patch.object(export, "load_metrics",
                               return_value={mid: SAMPLE["model-x"]}):
            text = export.export_csv()
        self.assertIn("'=HYPERLINK(1)", text.splitlines()[1])

    def test_html_to_file(self):
        path = os.path.join(self.tmp.name, "out.html")
        self.assertEqual(export.export_html(path), path)
        with open(path, encoding="utf-8") as f:
            self.assertIn("ReformBoss Dashboard", f.read())


if __name__ == "__main__":
    unittest.main()