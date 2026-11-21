"""Управление историей метрик: загрузка, сохранение, агрегация."""

import json
import os
from datetime import datetime

from rb_tui.utils import METRICS_HISTORY, MAX_HISTORY, CACHE


def load_metrics():
    try:
        with open(METRICS_HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_metrics(metrics):
    with open(METRICS_HISTORY, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def add_metric(metrics, model_id, status, ttft, total_time, tokens, fingerprint=""):
    if model_id not in metrics:
        metrics[model_id] = []
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": status,
        "ttft": ttft,
        "total_time": total_time,
        "tokens": tokens,
    }
    if fingerprint:
        entry["fp"] = fingerprint
    metrics[model_id].append(entry)
    metrics[model_id] = metrics[model_id][-MAX_HISTORY:]
    return metrics


def model_status(metrics, model_id):
    """Статус на основе истории: stable / unstable / dead / unknown."""
    hist = metrics.get(model_id, [])
    if not hist:
        return "unknown"
    ok = sum(1 for h in hist if h["status"] == "OK")
    recent = hist[-10:] if len(hist) >= 10 else hist
    recent_ok = sum(1 for h in recent if h["status"] == "OK")
    recent_rate = recent_ok / len(recent) if recent else 0

    if recent_rate >= 0.8 and ok >= 3:
        return "stable"
    elif recent_rate >= 0.3:
        return "unstable"
    else:
        return "dead"


def avg_ttft(metrics, model_id):
    """Средний TTFT среди успешных запросов."""
    hist = metrics.get(model_id, [])
    ok_ttfts = [h["ttft"] for h in hist if h["status"] == "OK" and h["ttft"] is not None]
    if not ok_ttfts:
        return None
    return round(sum(ok_ttfts) / len(ok_ttfts), 3)


def success_rate(metrics, model_id):
    """Процент успешных запросов."""
    hist = metrics.get(model_id, [])
    if not hist:
        return None
    ok = sum(1 for h in hist if h["status"] == "OK")
    return round(ok / len(hist) * 100)


def shortest_ttft(metrics, model_id):
    """Минимальный TTFT."""
    hist = metrics.get(model_id, [])
    ok_ttfts = [h["ttft"] for h in hist if h["status"] == "OK" and h["ttft"] is not None]
    if not ok_ttfts:
        return None
    return round(min(ok_ttfts), 3)


def full_stats(metrics, model_id):
    """Полная статистика по модели."""
    hist = metrics.get(model_id, [])
    if not hist:
        return None
    total = len(hist)
    ok = sum(1 for h in hist if h["status"] == "OK")
    err = sum(1 for h in hist if h["status"] == "ERR")
    no = sum(1 for h in hist if h["status"] == "NO")
    ok_ttfts = [h["ttft"] for h in hist if h["status"] == "OK" and h["ttft"] is not None]
    avg_t = round(sum(ok_ttfts) / len(ok_ttfts), 3) if ok_ttfts else None
    min_t = round(min(ok_ttfts), 3) if ok_ttfts else None
    max_t = round(max(ok_ttfts), 3) if ok_ttfts else None

    fp_changes = set()
    for h in hist:
        if h.get("fp"):
            fp_changes.add(h["fp"])

    return {
        "total": total,
        "ok": ok,
        "err": err,
        "no": no,
        "success_rate": round(ok / total * 100) if total else 0,
        "avg_ttft": avg_t,
        "min_ttft": min_t,
        "max_ttft": max_t,
        "fingerprints": list(fp_changes),
        "status": model_status(metrics, model_id),
        "first_seen": hist[0]["ts"],
        "last_seen": hist[-1]["ts"],
    }


def lifetime(metrics):
    """Когда каждая модель появилась / последний раз видна."""
    result = {}
    for mid, hist in metrics.items():
        if not hist:
            continue
        first = hist[0]["ts"]
        last = hist[-1]["ts"]
        count = len(hist)
        ok = sum(1 for h in hist if h["status"] == "OK")
        result[mid] = {
            "first_seen": first,
            "last_seen": last,
            "checks": count,
            "successful": ok,
        }
    return result


def find_anomalies(metrics, threshold=1.5):
    """Найти модели с аномалиями: резкий скачок TTFT или падение success rate."""
    anomalies = []
    for mid, hist in metrics.items():
        if len(hist) < 4:
            continue
        ok_ttfts = [h["ttft"] for h in hist if h["status"] == "OK" and h["ttft"] is not None]
        if len(ok_ttfts) < 4:
            continue

        recent = ok_ttfts[-2:]
        older = ok_ttfts[:-2]
        avg_older = sum(older) / len(older) if older else 0
        avg_recent = sum(recent) / len(recent) if recent else 0

        if avg_older > 0 and avg_recent > avg_older * threshold:
            anomalies.append({
                "model": mid,
                "type": "ttft_spike",
                "avg_older": round(avg_older, 3),
                "avg_recent": round(avg_recent, 3),
                "ratio": round(avg_recent / avg_older, 2),
            })

        # Падение success rate
        recent_hist = hist[-5:]
        older_hist = hist[:-5]
        if older_hist and recent_hist:
            recent_rate = sum(1 for h in recent_hist if h["status"] == "OK") / len(recent_hist)
            older_rate = sum(1 for h in older_hist if h["status"] == "OK") / len(older_hist)
            if older_rate > 0.7 and recent_rate < older_rate * 0.5:
                anomalies.append({
                    "model": mid,
                    "type": "success_drop",
                    "older_rate": round(older_rate, 2),
                    "recent_rate": round(recent_rate, 2),
                })

    return anomalies


def health_score(metrics):
    """Общий health score провайдера: 0-100."""
    models = list(metrics.keys())
    if not models:
        return 50
    scores = []
    for mid in models:
        s = 0
        st = model_status(metrics, mid)
        if st == "stable":
            s += 40
        elif st == "unstable":
            s += 15
        rate = success_rate(metrics, mid) or 0
        s += rate * 0.3
        avg_t = avg_ttft(metrics, mid)
        if avg_t is not None:
            if avg_t < 1:
                s += 20
            elif avg_t < 3:
                s += 10
            elif avg_t < 5:
                s += 5
        scores.append(s)
    return round(sum(scores) / len(scores))
