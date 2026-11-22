"""Защита от блокировок API: cooldown, бюджет проб и ротация моделей.

ReformBoss (new-api/oneapi gateway) считает массовое зондирование каталога
подозрительным и может временно заблокировать сессию
(`catalog_probe_detected`, `token_concurrency_limit`).

Поэтому пробы идут маленькими порциями, только по моделям из живого каталога,
с ротацией «кого давно не проверяли» и паузой между запросами. При первом же
признаке детекта прогон останавливается, а инструмент уходит в cooldown.
"""

import json
import os
import random
import time
from datetime import datetime

from rb_tui.utils import CACHE, atomic_write

PROBE_STATE = os.path.join(CACHE, "probe-state.json")


def _env_float(name, default):
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name, default):
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


# ── настройки (можно переопределить переменными окружения) ──
DEFAULT_BUDGET = _env_int("REFORMBOSS_PROBE_BUDGET", 10)
DEFAULT_DELAY = _env_float("REFORMBOSS_PROBE_DELAY", 3.0)
DEFAULT_COOLDOWN = _env_int("REFORMBOSS_COOLDOWN", 6 * 3600)
DEFAULT_DAILY_BUDGET = _env_int("REFORMBOSS_DAILY_BUDGET", 80)


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _empty_state():
    return {
        "cooldown_until": 0,
        "reason": "",
        "last_run": 0,
        "last_probe": {},
        "detections": 0,
        "total_probes": 0,
        "day": "",
        "day_probes": 0,
    }


def load_state():
    try:
        with open(PROBE_STATE, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = _empty_state()
    base = _empty_state()
    base.update(state)
    if not isinstance(base.get("last_probe"), dict):
        base["last_probe"] = {}
    return base


def save_state(state):
    atomic_write(PROBE_STATE, json.dumps(state, ensure_ascii=False, indent=2))


def cooldown_remaining(state=None):
    """Сколько секунд осталось до конца cooldown (0 — можно пробовать)."""
    state = state or load_state()
    return max(0, int(state.get("cooldown_until", 0) - time.time()))


def human_left(seconds):
    if seconds >= 3600:
        return f"{seconds // 3600} ч {seconds % 3600 // 60} мин"
    if seconds >= 60:
        return f"{seconds // 60} мин"
    return f"{seconds} сек"


def set_cooldown(seconds=None, reason=""):
    """Заблокировать пробы на N секунд (по умолчанию 6 часов)."""
    seconds = DEFAULT_COOLDOWN if seconds is None else seconds
    state = load_state()
    state["cooldown_until"] = time.time() + seconds
    state["reason"] = reason
    state["detections"] = int(state.get("detections", 0)) + 1
    save_state(state)
    return seconds


def clear_cooldown():
    state = load_state()
    state["cooldown_until"] = 0
    state["reason"] = ""
    save_state(state)


def cooldown_status_line():
    """Готовая строка для CLI или None, если блокировки нет."""
    state = load_state()
    left = cooldown_remaining(state)
    if left <= 0:
        return None
    reason = state.get("reason") or "сработала защита API"
    return (f"пробы на паузе ещё {human_left(left)} ({reason}). "
            f"Снять досрочно: rb-tui --probe-reset")


def daily_used(state=None):
    state = state or load_state()
    if state.get("day") != _today():
        return 0
    return int(state.get("day_probes", 0))


def daily_remaining(state=None):
    return max(0, DEFAULT_DAILY_BUDGET - daily_used(state))


def clamp_budget(budget):
    """Урезать порцию так, чтобы не превысить суточный лимит."""
    return max(0, min(budget, daily_remaining()))


def pick_targets(live, budget=None):
    """Выбрать модели для прогона: только из каталога, кого давно не проверяли.

    Возвращает список не длиннее budget. Порядок — от самой «забытой».
    """
    budget = DEFAULT_BUDGET if budget is None else budget
    state = load_state()
    last = state.get("last_probe", {})
    now = time.time()

    def age(mid):
        ts = last.get(mid)
        return now - ts if ts else float("inf")

    ordered = sorted(live, key=lambda m: (-age(m), m))
    # непроверенные (age = inf) идут первыми, дальше — самые «забытые»
    return ordered[:budget]


def mark_probed(models, count=None):
    """Запомнить, когда модели проверяли в последний раз.

    count — сколько реальных запросов ушло (bench/compare тратят несколько
    запросов на одну модель). По умолчанию — по одному на модель.
    """
    state = load_state()
    now = time.time()
    today = _today()
    if state.get("day") != today:
        state["day"] = today
        state["day_probes"] = 0
    for mid in models:
        state["last_probe"][mid] = now
    state["last_run"] = now
    spent = len(models) if count is None else max(0, int(count))
    state["total_probes"] = int(state.get("total_probes", 0)) + spent
    state["day_probes"] = int(state.get("day_probes", 0)) + spent
    # подчистить записи о моделях, которых больше нет в каталоге
    cutoff = now - 90 * 86400
    state["last_probe"] = {k: v for k, v in state["last_probe"].items()
                           if isinstance(v, (int, float)) and v >= cutoff}
    save_state(state)


def can_reserve(count):
    """Проверить cooldown и бюджет, не списывая запросы."""
    count = max(0, int(count))
    line = cooldown_status_line()
    if line:
        return False, line
    remaining = daily_remaining()
    if remaining < count:
        return False, (f"суточный лимит проб: осталось {remaining}, "
                       f"нужно {count}. Продолжу завтра.")
    return True, ""


def commit(count, models=None):
    """Списать бюджет после реально выполненных запросов."""
    mark_probed(models or [], count=count)


def reserve(count, models=None):
    """Проверить и списать бюджет заранее (для вызовов без учёта failures)."""
    ok, msg = can_reserve(count)
    if ok:
        commit(count, models)
    return ok, msg


def jitter(delay):
    """Небольшой разброс паузы, чтобы запросы не шли строго по метроному."""
    return delay + random.uniform(0, max(0.3, delay * 0.4))


def stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")