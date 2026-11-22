"""Сборка данных для дашборда: без HTML, без сети, легко тестируется."""

from datetime import datetime

from rb_tui.metrics import full_stats, health_score


STATUS_ORDER = {"stable": 0, "unstable": 1, "dead": 2, "unknown": 3}


def _avg(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def build_view(metrics, owned=None, tags=None):
    """Представление метрик для /api/view и стартовой страницы."""
    owned = owned or {}
    tags = tags or {}
    models = []
    counts = {"stable": 0, "unstable": 0, "dead": 0, "unknown": 0}
    checks = 0

    for mid, hist in metrics.items():
        stats = full_stats(metrics, mid)
        if not stats:
            continue
        counts[stats["status"]] = counts.get(stats["status"], 0) + 1
        checks += stats["total"]
        models.append({
            "id": mid,
            "status": stats["status"],
            "success_rate": stats["success_rate"],
            "avg_ttft": stats["avg_ttft"],
            "min_ttft": stats["min_ttft"],
            "max_ttft": stats["max_ttft"],
            "avg_tts": stats.get("avg_tts"),
            "avg_tps": stats.get("avg_tps"),
            "min_tps": stats.get("min_tps"),
            "max_tps": stats.get("max_tps"),
            "total": stats["total"],
            "ok": stats["ok"],
            "err": stats["err"],
            "no": stats["no"],
            "owner": owned.get(mid, ""),
            "tag": tags.get(mid, ""),
            "last_status": stats.get("last_status", ""),
            "last_error": stats.get("last_error", ""),
            "fp_changed": bool(stats.get("fp_changed")),
            "first_seen": stats["first_seen"],
            "last_seen": stats["last_seen"],
        })

    models.sort(key=lambda m: (
        STATUS_ORDER.get(m["status"], 9),
        m["avg_ttft"] is None,
        m["avg_ttft"] or 0,
        m["id"],
    ))

    return {
        "generated_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "health": health_score(metrics),
        "counts": counts,
        "checks": checks,
        "averages": {
            "ttft": _avg(m["avg_ttft"] for m in models),
            "tts": _avg(m["avg_tts"] for m in models),
            "tps": _avg(m["avg_tps"] for m in models),
            "success": _avg(m["success_rate"] for m in models),
        },
        "fp_changed": sum(1 for m in models if m["fp_changed"]),
        "models": models,
    }


def build_model_detail(metrics, model_id, history=None, limit=40):
    """Карточка модели для /api/model/<id>: статистика + последние пробы."""
    stats = full_stats(metrics, model_id)
    if not stats:
        return None
    entries = [e for e in (history or []) if e.get("model") == model_id]
    if not entries:
        entries = [dict(h, model=model_id) for h in metrics.get(model_id, [])]
    entries = entries[-limit:]
    return {
        "model": model_id,
        "stats": stats,
        "history": entries,
    }