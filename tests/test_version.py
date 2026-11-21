"""Тесты версии: нормализация PEP 440 и наличие VERSION."""

import os
import re
import unittest

import rb_tui


class PrettyVersionTest(unittest.TestCase):
    def test_pep440_to_readable(self):
        self.assertEqual(rb_tui._pretty_version("0.2.0b2"), "0.2.0-beta.2")
        self.assertEqual(rb_tui._pretty_version("1.4.2rc1"), "1.4.2-rc.1")
        self.assertEqual(rb_tui._pretty_version("3.13.0a3"), "3.13.0-alpha.3")

    def test_already_readable_is_unchanged(self):
        self.assertEqual(rb_tui._pretty_version("0.2.0-beta.2"), "0.2.0-beta.2")

    def test_release_is_unchanged(self):
        self.assertEqual(rb_tui._pretty_version("1.2.3"), "1.2.3")

    def test_empty_is_safe(self):
        self.assertEqual(rb_tui._pretty_version(None), None)


class VersionFileTest(unittest.TestCase):
    def test_version_is_not_unknown(self):
        self.assertNotEqual(rb_tui.__version__, "0.0.0-unknown")

    def test_version_looks_like_semver(self):
        self.assertRegex(rb_tui.__version__, r"^\d+\.\d+\.\d+")

    def test_version_file_is_single_line(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as f:
            value = f.read().strip()
        self.assertTrue(value)
        self.assertNotIn("\n", value)
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+", value))


if __name__ == "__main__":
    unittest.main()