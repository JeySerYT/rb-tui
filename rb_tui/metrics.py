"""Управление историей метрик: загрузка, сохранение, агрегация."""

import json
import os
from datetime import datetime

from rb_tui.utils import (
    METRICS_HISTORY, METRICS_LOG, MAX_HISTORY, CACHE,
    atomic_write, append_jsonl,
)


def load_metrics():
    try:
        with open(METRICS_HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_metrics(metrics):
    atomic_write(METRICS_HISTORY, json.dumps(metrics, ensure_ascii=False, indent=2))


def add_metric(metrics, model_id, status, ttft, total_time, tokens, fingerprint="", msg="", tts=None):
    if model_id not in metrics:
        metrics[model_id] = []
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": status,
        "ttft": ttft,
        "total_time": total_time,
        "tokens": tokens,
    }
    if tts is not None:
        entry["tts"] = tts
        # Эффективный throughput: завершённые токены за всё время ответа.
        # Окно «после первого токена» у буферизующих шлюзов даёт мусор.
        if tokens and total_time:
            entry["tps"] = round(tokens / total_time, 1)
    if fingerprint:
        entry["fp"] = fingerprint
        prev = next(
            (h.get("fp") for h in reversed(metrics[model_id]) if h.get("fp")),
            None,
        )
        if prev and prev != fingerprint:
            entry["fp_changed"] = {"from": prev, "to": fingerprint}
    if msg:
        entry["msg"] = msg
    metrics[model_id].append(entry)
    metrics[model_id] = metrics[model_id][-MAX_HISTORY:]
    return metrics


def record_metric(metrics, model_id, status, ttft, total_time, tokens,
                  fingerprint="", msg="", tts=None):
    """add_metric + полная история в JSONL. Используется CLI-пробами."""
    metrics = add_metric(
        metrics, model_id, status, ttft, total_time, tokens,
        fingerprint=fingerprint, msg=msg, tts=tts,
    )
    entry = dict(metrics[model_id][-1])
    entry["model"] = model_id
    append_jsonl(METRICS_LOG, entry)
    return metrics


def load_history(model_id=None, limit=None):
    """Прочитать полную историю из JSONL.

    limit — только последние N записей (для одного графика/карточки).
    Если архива ещё нет, отдаём горячий хвост из metrics.json.
    """
    entries = []
    try:
        with open(METRICS_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if model_id is not None and item.get("model") != model_id:
                    continue
                entries.append(item)
    except OSError:
        pass

    if not entries:
        data = load_metrics()
        if model_id is not None:
            entries = [dict(h, model=model_id) for h in data.get(model_id, [])]
        else:
            entries = [
                dict(h, model=mid)
                for mid, hist in data.items()
                for h in hist
            ]

    if limit is not None and limit > 0:
        entries = entries[-limit:]
    return entries


def prune_history(days=90):
    """Удалить из JSONL записи старше N дней. Возвращает (оставлено, удалено)."""
    cutoff = datetime.now().timestamp() - days * 86400
    kept, removed = [], 0
    try:
        with open(METRICS_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    ts = datetime.strptime(item.get("ts", ""), "%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    removed += 1
                    continue
                if ts.timestamp() >= cutoff:
                    kept.append(line)
                else:
                    removed += 1
    except OSError:
        return 0, 0
    if removed:
        atomic_write(METRICS_LOG, "\n".join(kept) + ("\n" if kept else ""))

    # Горячий хвост тоже чистим, иначе старые записи вернутся в статистику
    # и в fallback load_history().
    data = load_metrics()
    changed = False
    for mid in list(data):
        fresh = []
        for h in data[mid]:
            try:
                ts = datetime.strptime(h.get("ts", ""), "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                fresh.append(h)
                continue
            if ts.timestamp() >= cutoff:
                fresh.append(h)
            else:
                changed = True
        if fresh:
            data[mid] = fresh
        else:
            del data[mid]
            changed = True
    if changed:
        save_metrics(data)

    return len(kept), removed


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


def avg_tts(metrics, model_id):
    """Среднее время до второго токена (только стриминговые замеры)."""
    hist = metrics.get(model_id, [])
    vals = [h["tts"] for h in hist if h["status"] == "OK" and h.get("tts") is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 3)


def avg_tps(metrics, model_id):
    """Средняя скорость генерации, токенов в секунду."""
    hist = metrics.get(model_id, [])
    vals = [h["tps"] for h in hist if h["status"] == "OK" and h.get("tps") is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


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

    ok_tts = [h["tts"] for h in hist if h["status"] == "OK" and h.get("tts") is not None]
    avg_s = round(sum(ok_tts) / len(ok_tts), 3) if ok_tts else None
    min_s = round(min(ok_tts), 3) if ok_tts else None
    max_s = round(max(ok_tts), 3) if ok_tts else None

    ok_tps = [h["tps"] for h in hist if h["status"] == "OK" and h.get("tps") is not None]
    avg_p = round(sum(ok_tps) / len(ok_tps), 1) if ok_tps else None
    min_p = round(min(ok_tps), 1) if ok_tps else None
    max_p = round(max(ok_tps), 1) if ok_tps else None

    fp_changes = set()
    for h in hist:
        if h.get("fp"):
            fp_changes.add(h["fp"])

    last_error = ""
    for h in reversed(hist):
        if h["status"] != "OK" and h.get("msg"):
            last_error = h["msg"]
            break

    last_fp_change = None
    for h in reversed(hist):
        if h.get("fp_changed"):
            last_fp_change = h["fp_changed"]
            break

    return {
        "total": total,
        "ok": ok,
        "err": err,
        "no": no,
        "success_rate": round(ok / total * 100) if total else 0,
        "avg_ttft": avg_t,
        "min_ttft": min_t,
        "max_ttft": max_t,
        "avg_tts": avg_s,
        "min_tts": min_s,
        "max_tts": max_s,
        "avg_tps": avg_p,
        "min_tps": min_p,
        "max_tps": max_p,
        "fingerprints": list(fp_changes),
        "fp_changed": last_fp_change,
        "last_status": hist[-1]["status"],
        "last_error": last_error,
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


def find_anomalies(metrics, threshold=1.5, min_delta=0.3):
    """Найти аномалии: скачок TTFT/TTS, падение TPS или success rate,
    а также смену fingerprint (провайдер подменил модель)."""
    anomalies = []
    for mid, hist in metrics.items():
        if len(hist) < 4:
            continue

        ok_ttfts = [h["ttft"] for h in hist if h["status"] == "OK" and h["ttft"] is not None]
        if len(ok_ttfts) >= 4:
            recent = ok_ttfts[-2:]
            older = ok_ttfts[:-2]
            avg_older = sum(older) / len(older)
            avg_recent = sum(recent) / len(recent)
            if (avg_older > 0 and avg_recent > avg_older * threshold
                    and avg_recent - avg_older >= min_delta):
                anomalies.append({
                    "model": mid,
                    "type": "ttft_spike",
                    "avg_older": round(avg_older, 3),
                    "avg_recent": round(avg_recent, 3),
                    "ratio": round(avg_recent / avg_older, 2),
                })

        ok_tts = [h["tts"] for h in hist if h["status"] == "OK" and h.get("tts") is not None]
        if len(ok_tts) >= 4:
            recent = ok_tts[-2:]
            older = ok_tts[:-2]
            avg_older = sum(older) / len(older)
            avg_recent = sum(recent) / len(recent)
            if (avg_older > 0 and avg_recent > avg_older * threshold
                    and avg_recent - avg_older >= min_delta / 2):
                anomalies.append({
                    "model": mid,
                    "type": "tts_spike",
                    "avg_older": round(avg_older, 3),
                    "avg_recent": round(avg_recent, 3),
                    "ratio": round(avg_recent / avg_older, 2),
                })

        ok_tps = [h["tps"] for h in hist if h["status"] == "OK" and h.get("tps") is not None]
        if len(ok_tps) >= 4:
            recent = ok_tps[-2:]
            older = ok_tps[:-2]
            avg_older = sum(older) / len(older)
            avg_recent = sum(recent) / len(recent)
            if avg_older > 0 and avg_recent < avg_older * 0.6 and avg_older - avg_recent >= 1.0:
                anomalies.append({
                    "model": mid,
                    "type": "tps_drop",
                    "avg_older": round(avg_older, 1),
                    "avg_recent": round(avg_recent, 1),
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

        # Смена fingerprint — сигнал, что под тем же именем отдают другую модель.
        fp_change = None
        for h in reversed(hist[-5:]):
            if h.get("fp_changed"):
                fp_change = h["fp_changed"]
                break
        if fp_change:
            anomalies.append({
                "model": mid,
                "type": "fingerprint_change",
                "from": fp_change.get("from", ""),
                "to": fp_change.get("to", ""),
            })
        else:
            fps = [h["fp"] for h in hist if h.get("fp")]
            distinct = []
            for fp in fps:
                if fp not in distinct:
                    distinct.append(fp)
            if len(distinct) >= 2:
                anomalies.append({
                    "model": mid,
                    "type": "fingerprint_change",
                    "from": distinct[0],
                    "to": distinct[-1],
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
                s += 15
            elif avg_t < 5:
                s += 8
        avg_p = avg_tps(metrics, mid)
        if avg_p is not None:
            if avg_p >= 20:
                s += 10
            elif avg_p >= 10:
                s += 5
        scores.append(min(s, 100))
    return round(sum(scores) / len(scores))
