"""Тесты извлечения секции CHANGELOG для заметок релиза."""

import unittest

from scripts import release_notes

TEXT = """# Changelog

## 0.5.0-beta.2 (2026-11-22)

Новое.

- Пункт A
- Пункт B

## 0.5.0-beta.1 (2026-11-22)

Старое.

- Пункт C
"""


class ExtractTest(unittest.TestCase):
    def test_finds_section_by_tag(self):
        section = release_notes.extract(TEXT, "v0.5.0-beta.2")
        self.assertIn("Пункт A", section)
        self.assertNotIn("Пункт C", section)

    def test_accepts_version_without_v(self):
        section = release_notes.extract(TEXT, "0.5.0-beta.1")
        self.assertIn("Пункт C", section)
        self.assertNotIn("Пункт A", section)

    def test_missing_section_is_empty(self):
        self.assertEqual(release_notes.extract(TEXT, "v9.9.9"), "")

    def test_does_not_match_prefix(self):
        self.assertEqual(release_notes.extract(TEXT, "v0.5.0-beta"), "")


if __name__ == "__main__":
    unittest.main()