"""Уведомления: desktop, webhook, алерты."""

import json
import os
import platform
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


def _run(cmd, timeout=5, env=None):
    try:
        p = subprocess.run(cmd, timeout=timeout, capture_output=True, env=env)
        return p.returncode == 0
    except Exception:
        return False


def _notify_linux(title, message, urgency):
    if shutil.which("notify-send") is None:
        return False
    return _run(["notify-send", "--urgency", urgency, title, message])


def _notify_macos(title, message, urgency):
    if shutil.which("osascript") is None:
        return False
    # Аргументы через `--`: не нужно экранировать кавычки в тексте.
    script = (
        "on run argv\n"
        "display notification (item 2 of argv) with title (item 1 of argv)\n"
        "end run"
    )
    return _run(["osascript", "-e", script, "--", title, message])


_TOAST_SCRIPT = (
    "$ErrorActionPreference = 'Stop'\n"
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
    "ContentType = WindowsRuntime] | Out-Null\n"
    "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
    "ContentType = WindowsRuntime] | Out-Null\n"
    "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
    "$title = [System.Security.SecurityElement]::Escape($env:RB_TUI_NOTIFY_TITLE)\n"
    "$text = [System.Security.SecurityElement]::Escape($env:RB_TUI_NOTIFY_MESSAGE)\n"
    "$xml.LoadXml('<toast><visual><binding template=\"ToastText02\"><text id=\"1\">' + "
    "$title + '</text><text id=\"2\">' + $text + '</text></binding></visual></toast>')\n"
    "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml\n"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
    "'rb-tui').Show($toast)\n"
)


def _notify_windows(title, message, urgency):
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        return False
    env = dict(os.environ)
    env["RB_TUI_NOTIFY_TITLE"] = title
    env["RB_TUI_NOTIFY_MESSAGE"] = message
    return _run(
        [exe, "-NoProfile", "-NonInteractive", "-Command", _TOAST_SCRIPT],
        timeout=10, env=env,
    )


def desktop_notify(title, message, urgency="normal", system=None):
    """Desktop-уведомление средствами текущей ОС. True при успехе."""
    name = (system or platform.system()).lower()
    if name == "windows":
        return _notify_windows(title, message, urgency)
    if name == "darwin":
        return _notify_macos(title, message, urgency)
    return _notify_linux(title, message, urgency)


def notify_hint(system=None):
    """Что проверить, если уведомление не ушло."""
    name = (system or platform.system()).lower()
    if name == "windows":
        return "проверь уведомления Windows и доступность PowerShell"
    if name == "darwin":
        return "разреши уведомления для Терминала в Настройках macOS"
    return "проверь notify-send и права на DBus"


def test_notify():
    """Диагностика уведомлений для --test-notify."""
    return desktop_notify(
        "rb-tui: проверка уведомлений",
        "Если ты это видишь — desktop-уведомления работают.",
    )


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
                f"Success rate упал ({a['older_rate'] * 100}% → {a['recent_rate'] * 100}%)",
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
            lines.append(
                f"⚠ {a['model']}: success {a['older_rate'] * 100}% → {a['recent_rate'] * 100}%"
            )
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