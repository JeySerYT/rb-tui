"""Уведомления: desktop, webhook, алерты."""

import json
import os
import subprocess
import urllib.request
from datetime import datetime

from rb_tui.metrics import load_metrics, model_status, find_anomalies


def desktop_notify(title, message, urgency="normal"):
    """Desktop-уведомление через notify-send."""
    try:
        subprocess.run(
            ["notify-send", "--urgency", urgency, title, message],
            timeout=5, capture_output=True,
        )
    except Exception:
        pass  # не критично


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


def notify_stable_to_dead(metrics):
    """Если stable-модель стала dead — уведомить."""
    for mid in metrics:
        st = model_status(metrics, mid)
        if st != "dead":
            continue
        hist = metrics[mid]
        if hist and hist[-1].get("notified_dead"):
            continue
        # Проверим, была ли она раньше stable
        ok_old = sum(1 for h in hist[:-5] if h["status"] == "OK") if len(hist) > 5 else 0
        ok_recent = sum(1 for h in hist[-5:] if h["status"] == "OK") if hist else 0
        if ok_old > 3 and ok_recent == 0:
            notify_dead_model(mid)
            # Помечаем, что уведомили
            hist[-1]["notified_dead"] = True
            from rb_tui.metrics import save_metrics
            save_metrics(metrics)


def notify_anomalies(metrics=None):
    """Уведомить об аномалиях."""
    if metrics is None:
        metrics = load_metrics()
    anomalies = find_anomalies(metrics)
    for a in anomalies:
        if a["type"] == "ttft_spike":
            desktop_notify(
                f"⚠ ReformBoss: {a['model']}",
                f"TTFT вырос {a['ratio']}x ({a['avg_older']}s → {a['avg_recent']}s)",
                urgency="critical",
            )
        elif a["type"] == "success_drop":
            desktop_notify(
                f"⚠ ReformBoss: {a['model']}",
                f"Success rate упал ({a['older_rate']}% → {a['recent_rate']}%)",
                urgency="normal",
            )


def send_webhook(url, payload):
    """Отправить сводку на вебхук (Slack/Discord/Telegram)."""
    import json as j
    data = j.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
        return True
    except Exception:
        return False


def build_webhook_payload(metrics):
    """Сформировать payload для вебхука."""
    all_models = list(metrics.keys())
    ok_count = sum(1 for m in all_models if model_status(metrics, m) == "stable")
    dead_count = sum(1 for m in all_models if model_status(metrics, m) == "dead")
    anomalies = find_anomalies(metrics)

    blocks = [
        {
            "type": "header",
            "text": {"text": "🤖 ReformBoss Daily Report", "level": 1},
        },
        {
            "type": "section",
            "text": {
                "text": f"📊 Моделей: {len(all_models)}\n✅ Stable: {ok_count}\n❌ Dead: {dead_count}",
            },
        },
    ]

    if anomalies:
        anom_text = "\n".join(
            f"⚠ {a['model']}: {'TTFT spike' if a['type'] == 'ttft_spike' else 'Success drop'}"
            for a in anomalies[:5]
        )
        blocks.append({
            "type": "section",
            "text": {"text": f"🚨 *Аномалии:*\n{anom_text}"},
        })

    # Собираем payload в зависимости от формата (Slack)
    return {"text": None, "blocks": blocks}
