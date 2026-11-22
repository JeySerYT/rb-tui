"""Тесты API-клиента: схема URL проверяется до запроса."""

import unittest

from rb_tui import api


class HttpJsonTest(unittest.TestCase):
    def test_rejects_file_scheme(self):
        with self.assertRaises(ValueError):
            api.http_json("file:///etc/passwd", "key")


class FetchCatalogTest(unittest.TestCase):
    def test_ignores_malformed_entries(self):
        from unittest import mock
        payload = {"data": [
            {"id": "a", "owned_by": "x"},
            {"name": "no id"},
            None,
            {"id": ""},
            {"id": "b"},
        ]}
        with mock.patch.object(api, "http_json", return_value=payload):
            models, owned, err = api.fetch_catalog("https://x/v1", "k")
        self.assertEqual(models, ["a", "b"])
        self.assertEqual(owned, {"a": "x", "b": "unknown"})
        self.assertIsNone(err)
