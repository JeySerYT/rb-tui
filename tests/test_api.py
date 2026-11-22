"""Тесты API-клиента: схема URL проверяется до запроса."""

import unittest

from rb_tui import api


class HttpJsonTest(unittest.TestCase):
    def test_rejects_file_scheme(self):
        with self.assertRaises(ValueError):
            api.http_json("file:///etc/passwd", "key")
