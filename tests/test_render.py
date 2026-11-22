"""Тесты рендера интерактивного экрана и меню."""

import io
import unittest
from contextlib import redirect_stdout

from rb_tui import render


class RenderMenuTest(unittest.TestCase):
    def test_groups_keys_and_hint(self):
        out = io.StringIO()
        with redirect_stdout(out):
            render.render_menu([
                ("Каталог", "1", "добавить"),
                ("Инструменты", "c", "проверка конфига"),
            ])
        text = out.getvalue()
        self.assertIn("Каталог", text)
        self.assertIn("Инструменты", text)
        self.assertIn("1   добавить", text)
        self.assertIn("c   проверка конфига", text)
        self.assertIn("q — выход", text)


class RenderHomeTest(unittest.TestCase):
    def test_status_line(self):
        metrics = {"m": [{
            "ts": "2026-11-23T01:37:00+03:00", "status": "OK",
            "ttft": 1.0, "total_time": 1.0, "tokens": 3,
        }]}
        out = io.StringIO()
        with redirect_stdout(out):
            render.render_home(
                ["m"], ["m"], [], [], metrics, None, [], [],
                "https://x/v1", "1.2.3",
            )
        text = out.getvalue()
        self.assertIn("health:", text)
        self.assertIn("stable: 1", text)
        self.assertIn("проверок: 1", text)
        self.assertIn("rb-tui v1.2.3", text)


class ClockTest(unittest.TestCase):
    def test_iso_and_legacy(self):
        self.assertEqual(render._clock("2026-11-23T01:37:00+03:00"), "01:37")
        self.assertEqual(render._clock("2026-11-23 01:37"), "01:37")
