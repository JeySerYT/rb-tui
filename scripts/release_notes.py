#!/usr/bin/env python3
"""Напечатать секцию CHANGELOG.md для версии из тега.

    python scripts/release_notes.py v0.5.0-beta.2 > notes.md

Если секции нет, возвращает код 1 — CI тогда использует запасной вариант.
"""

import re
import sys
from pathlib import Path


def extract(text, version):
    version = (version or "").strip().lstrip("v")
    if not version:
        return ""
    # Заголовок может быть `## 1.2.3 (2026-01-01)` или `## [1.2.3] - 2026-01-01`.
    pattern = re.compile(
        rf"^##[ \t]+\[?v?{re.escape(version)}\]?(?![\w.-]).*?(?=^##[ \t]|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(0).strip() if match else ""


def main():
    if len(sys.argv) != 2:
        print("использование: release_notes.py <tag>", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parent.parent
    try:
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError as e:
        print(f"не читается CHANGELOG.md: {e}", file=sys.stderr)
        return 1
    section = extract(text, sys.argv[1])
    if not section:
        print(f"в CHANGELOG.md нет секции для {sys.argv[1]}", file=sys.stderr)
        return 1
    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())