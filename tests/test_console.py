"""Тесты консольной настройки: UTF-8, ANSI и пауза перед закрытием."""

import io
import os
import unittest
from unittest import mock

from rb_tui import console


class ReconfigureTest(unittest.TestCase):
    def test_stream_without_reconfigure_is_skipped(self):
        self.assertFalse(console._reconfigure(io.StringIO()))

    def test_stream_gets_utf8_and_replacement(self):
        stream = mock.Mock()
        self.assertTrue(console._reconfigure(stream))
        stream.reconfigure.assert_called_once_with(
            encoding="utf-8", errors="replace",
        )

    def test_failure_is_not_fatal(self):
        stream = mock.Mock()
        stream.reconfigure.side_effect = ValueError("closed")
        self.assertFalse(console._reconfigure(stream))

    def test_setup_returns_bool(self):
        self.assertIsInstance(console.setup(), bool)


class ColorTest(unittest.TestCase):
    def test_non_tty_has_no_color(self):
        self.assertFalse(console.can_color(mock.Mock(isatty=lambda: False)))

    def test_broken_stream_has_no_color(self):
        stream = mock.Mock()
        stream.isatty.side_effect = OSError("closed")
        self.assertFalse(console.can_color(stream))


class WaitTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "на Windows пауза включена")
    def test_no_pause_outside_windows(self):
        with mock.patch("builtins.input") as read:
            console.wait_before_exit()
        read.assert_not_called()


if __name__ == "__main__":
    unittest.main()