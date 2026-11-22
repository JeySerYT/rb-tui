"""Экспорт метрик: JSON, HTML, CSV."""

import csv
import io
import json
import os
from datetime import datetime
from html import escape

from rb_tui import __version__
from rb_tui.metrics import (
    load_metrics, full_stats, model_status, avg_ttft, success_rate, health_score,
)
from rb_tui.utils import CACHE

SCHEMA_VERSION = 1


def export_json(path=None):
    """Экспорт всех метрик в JSON."""
    metrics = load_metrics()
    stats = {}
    for mid in metrics:
        s = full_stats(metrics, mid)
        if s:
            stats[mid] = s

    payload = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "exported_at": datetime.now().isoformat(),
        "health_score": health_score(metrics),
        "total_models": len(metrics),
        "models": stats,
    }

    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path
    return json.dumps(payload, ensure_ascii=False, indent=2)


def export_csv(path=None):
    """Экспорт метрик в CSV."""
    metrics = load_metrics()
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([
        "model", "status", "success_rate", "avg_ttft", "avg_tts", "avg_tps",
        "min_ttft", "max_ttft", "total_checks", "ok", "err", "no",
    ])
    for mid in sorted(metrics.keys()):
        s = full_stats(metrics, mid)
        if not s:
            continue
        # Excel исполняет ячейки, начинающиеся с формулы, как выражение.
        safe_mid = "'" + mid if mid[:1] in ("=", "+", "-", "@") else mid
        writer.writerow([
            safe_mid, s["status"], s["success_rate"], s["avg_ttft"] or "",
            s["avg_tts"] or "", s["avg_tps"] or "",
            s["min_ttft"] or "", s["max_ttft"] or "",
            s["total"], s["ok"], s["err"], s["no"],
        ])

    csv_text = buf.getvalue()
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(csv_text)
        return path
    return csv_text


def export_html(path=None):
    """Экспорт красивого HTML-отчёта."""
    metrics = load_metrics()
    hs = health_score(metrics)

    rows = []
    for mid in sorted(metrics.keys()):
        s = full_stats(metrics, mid)
        if not s:
            continue
        status_color = {
            "stable": "#22c55e",
            "unstable": "#eab308",
            "dead": "#ef4444",
            "unknown": "#6b7280",
        }.get(s["status"], "#6b7280")

        avg_t = s["avg_ttft"] or "—"
        ttft_bar = ""
        if s["avg_ttft"]:
            bar_width = min(s["avg_ttft"] / 5 * 100, 100)
            ttft_bar = f'<div class="bar" style="width:{bar_width}%"></div>'
        avg_s = s["avg_tts"] or "—"
        avg_p = s["avg_tps"] or "—"

        first = escape(str(s["first_seen"]))
        last = escape(str(s["last_seen"]))
        rows.append(f"""
        <tr>
            <td><code>{escape(mid)}</code></td>
            <td><span class="badge" style="background:{status_color}">{escape(s["status"])}</span></td>
            <td>{s["success_rate"]}%</td>
            <td>{avg_t}s{ttft_bar}</td>
            <td>{avg_s}s</td>
            <td>{avg_p}</td>
            <td>{s["total"]} ({s["ok"]} OK / {s["err"]} ERR)</td>
            <td title="first: {first}, last: {last}">{first}</td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ReformBoss Dashboard</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:system-ui,-apple-system,sans-serif; background:#0f172a; color:#e2e8f0; padding:2rem; }}
  h1 {{ font-size:1.5rem; margin-bottom:0.5rem; }}
  .stats {{ display:flex; gap:1rem; margin:1.5rem 0; flex-wrap:wrap; }}
  .stat-card {{ background:#1e293b; padding:1rem 1.5rem; border-radius:12px; min-width:120px; }}
  .stat-card .num {{ font-size:2rem; font-weight:700; }}
  .stat-card .label {{ font-size:0.8rem; color:#94a3b8; }}
  table {{ width:100%; border-collapse:collapse; margin-top:1rem; }}
  th, td {{ text-align:left; padding:0.6rem 0.8rem; border-bottom:1px solid #1e293b; font-size:0.85rem; }}
  th {{ color:#94a3b8; font-weight:600; cursor:pointer; }}
  th:hover {{ color:#e2e8f0; }}
  tr:hover td {{ background:#1e293b; }}
  code {{ font-family:'JetBrains Mono','Fira Code',monospace; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:999px; color:#fff; font-size:0.75rem; font-weight:600; }}
  .bar {{ height:4px; background:#3b82f6; border-radius:2px; margin-top:4px; }}
  .footer {{ margin-top:2rem; font-size:0.8rem; color:#64748b; text-align:center; }}
  .green {{ color:#22c55e; }}
  .red {{ color:#ef4444; }}
</style>
</head>
<body>
<h1>🤖 ReformBoss Dashboard</h1>
<p style="color:#94a3b8;">{datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
<div class="stats">
  <div class="stat-card">
    <div class="num" style="color:#3b82f6;">{len(metrics)}</div>
    <div class="label">Моделей</div>
  </div>
  <div class="stat-card">
    <div class="num green">{sum(1 for m in metrics if model_status(metrics,m)=='stable')}</div>
    <div class="label">Stable</div>
  </div>
  <div class="stat-card">
    <div class="num" style="color:#eab308;">{sum(1 for m in metrics if model_status(metrics,m)=='unstable')}</div>
    <div class="label">Unstable</div>
  </div>
  <div class="stat-card">
    <div class="num red">{sum(1 for m in metrics if model_status(metrics,m)=='dead')}</div>
    <div class="label">Dead</div>
  </div>
  <div class="stat-card">
    <div class="num" style="color:{'#22c55e' if hs>=70 else '#eab308'}">{hs}</div>
    <div class="label">Health Score</div>
  </div>
</div>
<table id="table">
<thead>
  <tr><th>Модель</th><th>Статус</th><th>Success</th><th>TTFT</th><th>TTS</th><th>TPS</th><th>Проверки</th><th>Появилась</th></tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
<div class="footer">rb-tui · обновлено {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>
<script>
  // Сортировка по клику на заголовок
  document.querySelectorAll('th').forEach((th, i) => {{
    th.addEventListener('click', () => {{
      const tbody = document.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const dir = th.classList.toggle('asc') ? 1 : -1;
      rows.sort((a, b) => {{
        const ca = a.cells[i].textContent.trim();
        const cb = b.cells[i].textContent.trim();
        const na = parseFloat(ca), nb = parseFloat(cb);
        return (isNaN(na) || isNaN(nb) ? ca.localeCompare(cb) : na - nb) * dir;
      }});
      rows.forEach(r => tbody.appendChild(r));
    }});
  }});
</script>
</body>
</html>"""

    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path
    return html
