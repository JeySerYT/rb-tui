"""Автосинхронизация каталога с конфигом, бэкапы, rollback."""

import json
import os
import shutil
import sys
from datetime import datetime

from rb_tui.utils import (
    CACHE, STATE, MISSING, LOG, CONFIG,
    backup_config, prune_backups, parse_ok,
)
from rb_tui.config import apply_edits



def load_prev_catalog():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("date"), d.get("models")
    except Exception:
        return None, None


def save_catalog(models):
    d = {"date": datetime.now().strftime("%d.%m.%Y %H:%M"), "models": models}
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def load_missing():
    try:
        with open(MISSING, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_missing(d):
    with open(MISSING, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def log_auto(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def auto_sync(new, gone, live):
    try:
        prune_after = max(1, int(os.environ.get("REFORMBOSS_PRUNE_AFTER", "3")))
    except ValueError:
        prune_after = 3

    missing = load_missing()
    today = datetime.now().strftime("%Y-%m-%d")

    for mid in live:
        missing.pop(mid, None)

    for mid in gone:
        item = missing.get(mid)
        if isinstance(item, dict):
            item["count"] = int(item.get("count", 0)) + 1
        else:
            missing[mid] = {"count": 1, "since": today}

    known = set(live) | set(gone)
    missing = {m: v for m, v in missing.items() if m in known}

    to_prune = [m for m, v in missing.items()
                if isinstance(v, dict) and int(v.get("count", 0)) >= prune_after]

    save_missing(missing)

    if not new and not to_prune:
        tail = f", пропало={len(gone)} (ждут {prune_after})" if gone else ""
        log_auto(f"sync: каталог={len(live)}, новых нет{tail}")
        return

    date = datetime.now().strftime("%d.%m.%Y")
    ok, msg = apply_edits(adds=new, comment_out=to_prune, deletes=[], note_date=date)
    if ok:
        for mid in to_prune:
            missing.pop(mid, None)
        save_missing(missing)
        parts = [f"каталог={len(live)}", f"добавлено={len(new)}"]
        if gone:
            parts.append(f"пропало={len(gone)}")
        if to_prune:
            parts.append(f"удалено={len(to_prune)}")
        parts.append(f"бэкап={msg}")
        log_auto("sync: " + ", ".join(parts))
        if to_prune:
            log_auto("  - " + ", ".join(to_prune))
    else:
        log_auto(f"sync: ошибка правки: {msg}")
        sys.exit(1)


def auto_rollback():
    """Откатиться к последнему валидному бэкапу, если конфиг сломан."""
    bak_dir = os.path.dirname(CONFIG)
    baks = sorted([f for f in os.listdir(bak_dir) if f.startswith("opencode.json.bak-")],
                  reverse=True)
    for bak in baks:
        bak_path = os.path.join(bak_dir, bak)
        with open(bak_path, encoding="utf-8") as f:
            raw = f.read()
        if parse_ok(raw):
            # Делаем бэкап текущего (сломанного)
            backup_config()
            shutil.copy2(bak_path, CONFIG)
            log_auto(f"rollback: восстановлен {bak}")
            return True, bak
    return False, "нет валидных бэкапов"


def auto_cleanup(days=30):
    """Автоочистка бэкапов и старых логов."""
    pruned = prune_backups(days=days)
    if pruned:
        log_auto(f"cleanup: удалено {pruned} бэкапов старше {days} дней")
    return pruned
