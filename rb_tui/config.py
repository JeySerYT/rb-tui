"""Работа с opencode.json: чтение, правки, diff, проверка."""

import json
import os
import re

from rb_tui import utils
from rb_tui.utils import (
    STATE, strip_jsonc, parse_ok, pretty_name, backup_config,
    atomic_write, backup_prefix,
)


def read_raw():
    with open(utils.CONFIG, encoding="utf-8") as f:
        return f.read().lstrip("\ufeff")


def load_config():
    raw = read_raw()
    data = json.loads(strip_jsonc(raw))
    container = data.get("providers") or data.get("provider") or {}
    prov = container.get("reformboss", {})
    settings = prov.get("settings", {})
    models = prov.get("models", {}) or {}
    return raw, settings, list(models.keys())


def _skip_noise(raw, i):
    """Пропустить комментарий JSONC; вернуть новую позицию или None."""
    n = len(raw)
    if raw.startswith("//", i):
        j = raw.find("\n", i)
        return n if j < 0 else j
    if raw.startswith("/*", i):
        j = raw.find("*/", i + 2)
        return n if j < 0 else j + 2
    return None


def _scan_balanced(raw, open_idx):
    """Индекс закрывающей скобки для { или [ с учётом строк и комментариев."""
    pairs = {"{": "}", "[": "]"}
    if raw[open_idx] not in pairs:
        return None
    stack = []
    i, n, ins = open_idx, len(raw), False
    while i < n:
        ch = raw[i]
        if ins:
            if ch == "\\" and i + 1 < n:
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
        skipped = _skip_noise(raw, i)
        if skipped is not None:
            i = skipped
            continue
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in "}]":
            if not stack:
                return None
            stack.pop()
            if not stack:
                return i
        i += 1
    return None


def _scan_object_end(raw, open_idx):
    """Индекс закрывающей скобки для объекта, начинающегося с open_idx."""
    return _scan_balanced(raw, open_idx)


def _find_key_open(raw, key):
    """Позиция '{' после ключа, игнорируя строки и комментарии."""
    needle = '"' + key + '"'
    i, n = 0, len(raw)
    while i < n:
        ch = raw[i]
        skipped = _skip_noise(raw, i)
        if skipped is not None:
            i = skipped
            continue
        if ch != '"':
            i += 1
            continue
        j = i + 1
        while j < n:
            if raw[j] == "\\":
                j += 2
                continue
            if raw[j] == '"':
                break
            j += 1
        if raw[i:j + 1] == needle:
            k = j + 1
            while k < n and raw[k] in " \t\r\n":
                k += 1
            if k < n and raw[k] == ":":
                k += 1
                while k < n and raw[k] in " \t\r\n":
                    k += 1
                if k < n and raw[k] == "{":
                    return k
        i = j + 1
    return None


def _entry_span(raw, mid):
    """(начало, конец значения) записи '"mid": ...' в блоке models."""
    pat = re.compile(rf'(?m)^(?P<ind>[ \t]*)"{re.escape(mid)}"[ \t]*:')
    m = pat.search(raw)
    if not m:
        return None
    start, i, n = m.start(), m.end(), len(raw)
    while i < n and raw[i] in " \t":
        i += 1
    if i < n and raw[i] in "{[":
        end = _scan_balanced(raw, i)
        if end is None:
            return None
        return start, end + 1
    ins = False
    while i < n:
        ch = raw[i]
        if ch == "\\" and ins:
            i += 2
            continue
        if ch == '"':
            ins = not ins
        if not ins and ch in ",\n":
            break
        i += 1
    return start, i


def _entry_tail(raw, end):
    """(индекс запятой, индекс после перевода строки) после значения записи."""
    i = end
    while i < len(raw) and raw[i] in " \t":
        i += 1
    comma = i if i < len(raw) and raw[i] == "," else None
    if comma is not None:
        i += 1
    while i < len(raw) and raw[i] in " \t\r":
        i += 1
    if i < len(raw) and raw[i] == "\n":
        i += 1
    return comma, i


def find_models_span(raw):
    """Найти границы блока providers.reformboss.models в JSONC.

    Именно reformboss, а не первый попавшийся "models": иначе при нескольких
    провайдерах правки уйдут в чужой конфиг. Если структуру найти не удалось,
    откатываемся к старому поведению (первый блок models).
    """
    for container in ("providers", "provider"):
        top_open = _find_key_open(raw, container)
        if top_open is None:
            continue
        top_end = _scan_balanced(raw, top_open)
        if top_end is None:
            continue
        section = raw[top_open:top_end + 1]
        prov_rel = _find_key_open(section, "reformboss")
        if prov_rel is None:
            continue
        prov_open = top_open + prov_rel
        prov_end = _scan_balanced(raw, prov_open)
        if prov_end is None:
            continue
        models_rel = _find_key_open(raw[prov_open:prov_end + 1], "models")
        if models_rel is None:
            continue
        models_open = prov_open + models_rel
        models_end = _scan_balanced(raw, models_open)
        if models_end is not None:
            return models_open, models_end

    open_idx = _find_key_open(raw, "models")
    if open_idx is None:
        return None
    return open_idx, _scan_balanced(raw, open_idx)


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
        span = _entry_span(block, mid)
        if not span or block[span[0]:].lstrip().startswith("//"):
            continue
        start, end = span
        comma, _after = _entry_tail(block, end)
        text = block[start:comma] if comma is not None else block[start:end]
        lines = text.rstrip().splitlines()
        if not lines:
            continue
        ind = re.match(r"[ \t]*", lines[0]).group(0)
        repl = "\n".join(
            ind + "// " + line.strip()
            + (f"  // нет в каталоге с {note_date}" if idx == 0 else "")
            for idx, line in enumerate(lines)
        )
        block = block[:start] + repl + block[end:]
        delta = len(repl) - (end - start)
        if comma is not None:
            c = comma + delta
            block = block[:c] + block[c + 1:]
        changed = True

    for mid in deletes:
        span = _entry_span(block, mid)
        if not span:
            continue
        start, end = span
        _comma, tail_end = _entry_tail(block, end)
        block = block[:start] + block[tail_end:]
        changed = True

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
    atomic_write(utils.CONFIG, new_raw)
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
    atomic_write(utils.CONFIG, new_raw)
    return True, bak


def diff_with_last_backup():
    """Показать diff между последним бэкапом и текущим конфигом."""
    import difflib

    bak_dir = os.path.dirname(utils.CONFIG) or "."
    prefix = backup_prefix()
    baks = sorted([f for f in os.listdir(bak_dir) if f.startswith(prefix)])
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
        fromfile=f"backup/{baks[-1]}",
        tofile=f"current/{os.path.basename(utils.CONFIG)}",
        lineterm=""
    )
    return "\n".join(diff)


def config_check():
    """Проверить конфиг на проблемы: структуру, ключ, права, битые модели."""
    issues = []
    raw = read_raw()

    # Валидный JSON
    try:
        data = json.loads(strip_jsonc(raw))
    except json.JSONDecodeError as e:
        return [f"❌ JSON сломан: {e}"]

    if not find_models_span(raw):
        issues.append("❌ Не найден блок providers.reformboss.models")

    container = data.get("providers") or data.get("provider") or {}
    prov = container.get("reformboss", {})
    if not prov:
        issues.append("❌ Нет провайдера reformboss")
    models = prov.get("models", {}) or {}
    if not isinstance(models, dict):
        issues.append("❌ reformboss.models должен быть объектом")
        models = {}

    # Дубликаты (по имени, без учёта регистра)
    seen = {}
    for mid in models:
        normal = mid.lower().strip()
        if normal in seen:
            issues.append(f"⚠ Дубликат: '{mid}' — уже есть как '{seen[normal]}'")
        seen[normal] = mid
        if not mid.strip():
            issues.append("⚠ Пустой идентификатор модели")
        elif mid != mid.strip():
            issues.append(f"⚠ Пробелы по краям в имени модели: '{mid}'")

    # Настройки
    settings = prov.get("settings", {})
    if not isinstance(settings, dict):
        issues.append("❌ reformboss.settings должен быть объектом")
        settings = {}

    api_key = settings.get("apiKey")
    # На Windows биты прав синтетические: chmod 600 там нет и совет вводит в заблуждение.
    check_modes = os.name == "posix"
    if not api_key:
        issues.append("❌ Нет apiKey в настройках reformboss")
    else:
        m = re.match(r"\{file:(.+)\}", str(api_key))
        if m:
            key_path = os.path.expanduser(m.group(1))
            if not os.path.isfile(key_path):
                issues.append(f"❌ Файл с ключом не найден: {key_path}")
            elif check_modes:
                try:
                    mode = os.stat(key_path).st_mode
                    if mode & 0o077:
                        issues.append(
                            f"⚠ Файл с ключом доступен группе/остальным "
                            f"({oct(mode & 0o777)}): chmod 600 {key_path}"
                        )
                except OSError:
                    pass
        elif check_modes:
            try:
                mode = os.stat(utils.CONFIG).st_mode
                if mode & 0o004:
                    issues.append(
                        f"⚠ apiKey лежит прямо в конфиге, а файл читают все "
                        f"({oct(mode & 0o777)}): chmod 600 {utils.CONFIG}"
                    )
            except OSError:
                pass

    base = settings.get("baseURL", "")
    if not base:
        issues.append("❌ Нет baseURL в настройках reformboss")
    elif not re.match(r"^https?://", str(base)):
        issues.append(f"⚠ baseURL не похож на URL: {base}")

    # Модели без name / с пустым name
    for mid, val in models.items():
        if not isinstance(val, dict):
            issues.append(f"⚠ Модель '{mid}' должна быть объектом")
            continue
        if "name" not in val:
            issues.append(f"⚠ Модель '{mid}' без поля name")
        elif not str(val.get("name", "")).strip():
            issues.append(f"⚠ Модель '{mid}' с пустым name")

    # Сверка с последним сохранённым каталогом (без сети)
    try:
        with open(STATE, encoding="utf-8") as f:
            catalog = json.load(f).get("models") or []
        if catalog:
            absent = [m for m in models if m not in catalog]
            if absent:
                issues.append(
                    f"⚠ {len(absent)} моделей из конфига нет в последнем каталоге "
                    f"(мог устареть): {', '.join(absent[:5])}"
                    + (" …" if len(absent) > 5 else "")
                )
    except Exception:
        pass

    if not issues:
        issues.append("✅ Конфиг в порядке")

    return issues
