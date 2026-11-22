"""Уведомления: desktop, webhook, алерты."""

import json
import os
import shutil
import subprocess
import time
import urllib.request

from rb_tui.metrics import (
    load_metrics, model_status, find_anomalies, health_score,
)
from rb_tui.utils import CACHE, atomic_write

ALERTS_STATE = os.path.join(CACHE, "alerts-state.json")
DEDUP_HOURS = 12


def desktop_notify(title, message, urgency="normal"):
    """Desktop-уведомление через notify-send. Возвращает True при успехе."""
    if shutil.which("notify-send") is None:
        return False
    try:
        p = subprocess.run(
            ["notify-send", "--urgency", urgency, title, message],
            timeout=5, capture_output=True,
        )
        return p.returncode == 0
    except Exception:
        return False


def test_notify():
    """Диагностика уведомлений для --test-notify."""
    ok = desktop_notify(
        "rb-tui: проверка уведомлений",
        "Если ты это видишь — desktop-уведомления работают.",
    )
    return ok


def notify_new_models(new_models):
    """Уведомить о появлении новых моделей."""
    if not new_models:
        return
    msg = "\n".join(f"  + {m}" for m in new_models[:10])
    if len(new_models) > 10:
        msg += f"\n  ... и ещё {len(new_models) - 10}"
    desktop_notify(
        f"ReformBoss: {len(new_models)} новых моделей",
        msg,
        urgency="normal",
    )


def notify_dead_model(model_id):
    """Уведомить, что модель стала dead."""
    desktop_notify(
        f"⚠ ReformBoss: {model_id} недоступна",
        "Модель перестала отвечать. Проверь статус: rb-tui --info " + model_id,
        urgency="critical",
    )


def _load_alerted():
    try:
        with open(ALERTS_STATE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_alerted(data):
    atomic_write(ALERTS_STATE, json.dumps(data, ensure_ascii=False, indent=2))


def _should_notify(key, hours=DEDUP_HOURS):
    """Не повторять один и тот же алерт чаще, чем раз в N часов."""
    now = time.time()
    data = _load_alerted()
    cutoff = now - 30 * 86400
    data = {k: v for k, v in data.items()
            if isinstance(v, (int, float)) and v >= cutoff}
    last = data.get(key, 0)
    if now - last < hours * 3600:
        _save_alerted(data)
        return False
    data[key] = now
    _save_alerted(data)
    return True


def notify_stable_to_dead(metrics):
    """Если stable-модель стала dead — уведомить (не чаще раза в сутки)."""
    for mid in metrics:
        if model_status(metrics, mid) != "dead":
            continue
        hist = metrics[mid]
        ok_old = sum(1 for h in hist[:-5] if h["status"] == "OK") if len(hist) > 5 else 0
        ok_recent = sum(1 for h in hist[-5:] if h["status"] == "OK") if hist else 0
        if ok_old > 3 and ok_recent == 0 and _should_notify(f"dead:{mid}", 24):
            notify_dead_model(mid)


def _anomaly_key(a):
    if a["type"] == "fingerprint_change":
        return f"fp:{a['model']}:{a.get('from')}:{a.get('to')}"
    return f"{a['type']}:{a['model']}"


def notify_anomalies(metrics=None, dedup_hours=DEDUP_HOURS):
    """Уведомить об аномалиях, не повторяя одно и то же каждый --sync."""
    if metrics is None:
        metrics = load_metrics()
    for a in find_anomalies(metrics):
        if not _should_notify(_anomaly_key(a), dedup_hours):
            continue
        if a["type"] == "ttft_spike":
            desktop_notify(
                f"⚠ ReformBoss: {a['model']}",
                f"TTFT вырос {a['ratio']}x ({a['avg_older']}s → {a['avg_recent']}s)",
                urgency="critical",
            )
        elif a["type"] == "tts_spike":
            desktop_notify(
                f"⚠ ReformBoss: {a['model']}",
                f"TTS вырос {a['ratio']}x ({a['avg_older']}s → {a['avg_recent']}s)",
                urgency="normal",
            )
        elif a["type"] == "tps_drop":
            desktop_notify(
                f"⚠ ReformBoss: {a['model']}",
                f"TPS упал {a['ratio']}x ({a['avg_older']} → {a['avg_recent']} tok/s)",
                urgency="critical",
            )
        elif a["type"] == "success_drop":
            desktop_notify(
                f"⚠ ReformBoss: {a['model']}",
                f"Success rate упал ({a['older_rate']}% → {a['recent_rate']}%)",
                urgency="normal",
            )
        elif a["type"] == "fingerprint_change":
            desktop_notify(
                f"⚠ ReformBoss: {a['model']} подменили?",
                f"Сменился fingerprint: {a['from']} → {a['to']}",
                urgency="critical",
            )


def webhook_format(url):
    """Определить формат payload по хосту."""
    low = (url or "").lower()
    if "discord" in low:
        return "discord"
    if "hooks.slack" in low or "slack.com" in low:
        return "slack"
    if "telegram" in low:
        return "telegram"
    return "generic"


def send_webhook(url, payload, retries=2):
    """Отправить сводку на вебхук с парой повторов."""
    data = json.dumps(payload).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
            return True
        except Exception:
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    return False


def build_webhook_payload(metrics, fmt="slack"):
    """Сформировать payload для Slack / Discord / generic."""
    all_models = list(metrics.keys())
    ok_count = sum(1 for m in all_models if model_status(metrics, m) == "stable")
    dead_count = sum(1 for m in all_models if model_status(metrics, m) == "dead")
    anomalies = find_anomalies(metrics)
    hs = health_score(metrics)

    lines = [
        f"🤖 ReformBoss: {len(all_models)} моделей",
        f"✅ stable: {ok_count} · ❌ dead: {dead_count} · health: {hs}/100",
    ]
    for a in anomalies[:5]:
        if a["type"] == "fingerprint_change":
            lines.append(f"⚠ {a['model']}: сменился fingerprint")
        elif a["type"] == "tps_drop":
            lines.append(f"⚠ {a['model']}: TPS {a['avg_older']} → {a['avg_recent']}")
        elif a["type"] == "ttft_spike":
            lines.append(f"⚠ {a['model']}: TTFT ×{a['ratio']}")
        elif a["type"] == "tts_spike":
            lines.append(f"⚠ {a['model']}: TTS ×{a['ratio']}")
        elif a["type"] == "success_drop":
            lines.append(f"⚠ {a['model']}: success {a['older_rate']} → {a['recent_rate']}")
    text = "\n".join(lines)

    if fmt == "discord":
        return {"content": text}

    payload = {"text": text}
    if fmt == "slack":
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🤖 ReformBoss Daily Report"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            },
        ]
        payload["blocks"] = blocks
    return payload