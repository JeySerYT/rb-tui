"""HTTP-тесты дашборда на реальном локальном сервере (порт 0)."""

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from unittest import mock

from rb_tui import dashboard, metrics


def sample():
    data = {}
    for _ in range(3):
        data = metrics.add_metric(data, "alpha/model", "OK", 1.0, 2.0, 11, tts=1.5)
    return data


class DashboardHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        data = sample()
        for patcher in (
            mock.patch.object(dashboard, "load_metrics", return_value=data),
            mock.patch.object(dashboard, "load_catalog_owned", return_value={"alpha/model": "deepseek"}),
            mock.patch.object(dashboard, "load_tags", return_value={"alpha/model": "coding"}),
            mock.patch.object(dashboard, "load_history", return_value=[]),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as r:
            return r.status, r.headers, r.read().decode()

    def test_health_reports_version_and_uptime(self):
        status, _, body = self.get("/health")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "ok")
        self.assertIn("version", data)
        self.assertIn("uptime_seconds", data)

    def test_api_view_has_owner_tag_and_error_fields(self):
        status, _, body = self.get("/api/view")
        self.assertEqual(status, 200)
        model = json.loads(body)["models"][0]
        self.assertEqual(model["owner"], "deepseek")
        self.assertEqual(model["tag"], "coding")
        self.assertIn("last_error", model)

    def test_api_model_returns_detail(self):
        status, _, body = self.get("/api/model/alpha%2Fmodel")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["model"], "alpha/model")
        self.assertIn("history", data)

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/nope")
        self.assertEqual(ctx.exception.code, 404)
        ctx.exception.close()

    def test_index_has_drawer(self):
        status, _, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn('id="drawer"', body)


if __name__ == "__main__":
    unittest.main()