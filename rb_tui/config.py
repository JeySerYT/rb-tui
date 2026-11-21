"""Работа с opencode.json: чтение, правки, diff, проверка."""

import json
import os
import re
import shutil
from datetime import datetime

from rb_tui.utils import (
    CONFIG, CACHE, strip_jsonc, parse_ok, pretty_name, backup_config,
)


def read_raw():
    with open(CONFIG, encoding="utf-8") as f:
        return f.read().lstrip("\ufeff")


def load_config():
    raw = read_raw()
    data = json.loads(strip_jsonc(raw))
    prov = data.get("providers", {}).get("reformboss", {})
    settings = prov.get("settings", {})
    models = prov.get("models", {}) or {}
    return raw, settings, list(models.keys())


def find_models_span(raw):
    """Найти границы блока 'models' в JSONC."""
    m = re.search(r'"models"\s*:\s*\{', raw)
    if not m:
        return None
    open_idx = raw.rindex("{", m.start(), m.end())
    depth, i, n, ins = 0, open_idx, len(raw), False
    while i < n:
        ch = raw[i]
        if ins:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                ins = False
            i += 1
            continue
        if ch == '"':
            ins = True
            i += 1
            continue
        if raw.startswith("//", i):
            j = raw.find("\n", i)
            i = n if j < 0 else j
            continue
        if raw.startswith("/*", i):
            j = raw.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return open_idx, i
        i += 1
    return None


def indent_of_entry(raw, open_idx):
    after = raw[open_idx + 1:]
    m = re.search(r'\n(\s*)"', after)
    return m.group(1) if m else " " * 8


def apply_edits(adds, comment_out, deletes, note_date):
    """(ok, сообщение). Построчные правки, комментарии сохраняются."""
    raw = read_raw()
    span = find_models_span(raw)
    if not span:
        return False, "не нашёл блок models в конфиге"
    open_idx, close_idx = span
    before, block, after = raw[:open_idx + 1], raw[open_idx + 1:close_idx], raw[close_idx:]
    _, _, current = load_config()
    has_entries = len(current) > 0
    changed = False

    if adds:
        ind = indent_of_entry(raw, open_idx)
        lines = []
        for k, mid in enumerate(adds):
            comma = "," if (has_entries or k < len(adds) - 1) else ""
            lines.append(f'\n{ind}"{mid}": {{ "name": "{pretty_name(mid)}" }}{comma}')
        block = "".join(lines) + block
        changed = True

    for mid in comment_out:
        pat = re.compile(rf'^(?P<line>(?P<ind>\s*)"{re.escape(mid)}"\s*:.*?)$', re.M)
        m = pat.search(block)
        if m and not m.group("line").lstrip().startswith("//"):
            line = m.group("line").rstrip()
            if line.endswith(","):
                line = line[:-1] + " "
            repl = f'{m.group("ind")}// {line.strip()}  // нет в каталоге с {note_date}'
            block = block[:m.start()] + repl + block[m.end():]
            changed = True

    for mid in deletes:
        pat = re.compile(rf'^\s*"{re.escape(mid)}"\s*:.*\n?', re.M)
        block, n = pat.subn("", block)
        changed = changed or n > 0

    if changed and (comment_out or deletes):
        active = [m for m in re.finditer(r'^\s*"[^"]+"\s*:.*$', block, re.M)
                  if not m.group(0).lstrip().startswith("//")]
        if active:
            last = active[-1]
            fixed = re.sub(r',\s*$', "", last.group(0))
            block = block[:last.start()] + fixed + block[last.end():]

    if not changed:
        return False, "нечего менять"

    new_raw = before + block + after
    if not parse_ok(new_raw):
        return False, "правка сломала JSON, откат (файл не тронут)"

    bak = backup_config()
    with open(CONFIG, "w", encoding="utf-8") as f:
        f.write(new_raw)
    return True, bak


def append_log(lines):
    raw = read_raw()
    span = find_models_span(raw)
    if not span:
        return False, "не нашёл блок models"
    open_idx, close_idx = span
    ind = indent_of_entry(raw, open_idx)
    tail = raw[raw.rfind("\n", 0, close_idx) + 1:close_idx]
    insert = "".join(f"\n{ind}// {ln}" for ln in lines) + "\n" + tail
    new_raw = raw[:close_idx] + insert + raw[close_idx:]
    if not parse_ok(new_raw):
        return False, "лог ломает JSON, откат"
    bak = backup_config()
    with open(CONFIG, "w", encoding="utf-8") as f:
        f.write(new_raw)
    return True, bak


def diff_with_last_backup():
    """Показать diff между последним бэкапом и текущим конфигом."""
    import difflib

    bak_dir = os.path.dirname(CONFIG)
    baks = sorted([f for f in os.listdir(bak_dir) if f.startswith("opencode.json.bak-")])
    if not baks:
        return "нет бэкапов для сравнения"

    last_bak = os.path.join(bak_dir, baks[-1])
    with open(last_bak, encoding="utf-8") as f:
        old = strip_jsonc(f.read())
    new = strip_jsonc(read_raw())

    old_lines = old.splitlines()
    new_lines = new.splitlines()
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"backup/{baks[-1]}", tofile="current/opencode.json",
        lineterm=""
    )
    return "\n".join(diff)


def config_check():
    """Проверить конфиг на проблемы: дубликаты, битые модели."""
    issues = []
    raw = read_raw()

    # Валидный JSON
    try:
        data = json.loads(strip_jsonc(raw))
    except json.JSONDecodeError as e:
        return [f"❌ JSON сломан: {e}"]

    prov = data.get("providers", {}).get("reformboss", {})
    models = prov.get("models", {}) or {}

    # Дубликаты (по имени)
    seen = {}
    for mid in models:
        normal = mid.lower().strip()
        if normal in seen:
            issues.append(f"⚠ Дубликат: '{mid}' — уже есть как '{seen[normal]}'")
        seen[normal] = mid

    # Пустые настройки
    settings = prov.get("settings", {})
    if not settings.get("apiKey"):
        issues.append("❌ Нет apiKey в настройках reformboss")
    if not settings.get("baseURL"):
        issues.append("❌ Нет baseURL в настройках reformboss")

    # Модели без name (если есть другие поля — норм)
    for mid, val in models.items():
        if isinstance(val, dict) and "name" not in val:
            issues.append(f"⚠ Модель '{mid}' без поля name")

    if not issues:
        issues.append("✅ Конфиг в порядке")

    return issues
