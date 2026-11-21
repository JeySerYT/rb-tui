"""HTTP-дашборд: --serve"""

import json
import os
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from rb_tui.metrics import load_metrics, full_stats, model_status, avg_ttft, success_rate, health_score


class DashboardHandler(BaseHTTPRequestHandler):
    """Простой HTTP-сервер, отдающий HTML-дашборд."""

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            metrics = load_metrics()
            hs = health_score(metrics)
            self.wfile.write(json.dumps({
                "status": "ok",
                "health_score": hs,
                "models": len(metrics),
                "timestamp": datetime.now().isoformat(),
            }).encode())
            return

        if self.path == "/api/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            metrics = load_metrics()
            data = {}
            for mid in metrics:
                s = full_stats(metrics, mid)
                if s:
                    data[mid] = s
            self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode())
            return

        # HTML dashboard
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        metrics = load_metrics()
        hs = health_score(metrics)

        rows = []
        for mid in sorted(metrics.keys()):
            s = full_stats(metrics, mid)
            if not s:
                continue
            status_color = {
                "stable": "#22c55e", "unstable": "#eab308",
                "dead": "#ef4444", "unknown": "#6b7280",
            }.get(s["status"], "#6b7280")
            avg_t = s["avg_ttft"] or "—"
            bar = ""
            if s["avg_ttft"]:
                bar = f'<div class="bar" style="width:{min(s["avg_ttft"]/5*100,100)}%"></div>'
            rows.append(f"""
            <tr>
                <td><code>{mid}</code></td>
                <td><span class="badge" style="background:{status_color}">{s["status"]}</span></td>
                <td>{s["success_rate"]}%</td>
                <td>{avg_t}s{bar}</td>
                <td>{s["total"]} ({s["ok"]} OK)</td>
                <td>{s["first_seen"]}</td>
            </tr>""")

        html = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ReformBoss Live</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:system-ui,-apple-system,sans-serif; background:#0f172a; color:#e2e8f0; padding:2rem; }}
  h1 {{ font-size:1.5rem; }}
  .stats {{ display:flex; gap:1rem; margin:1.5rem 0; flex-wrap:wrap; }}
  .stat-card {{ background:#1e293b; padding:1rem 1.5rem; border-radius:12px; min-width:120px; }}
  .stat-card .num {{ font-size:2rem; font-weight:700; }}
  .stat-card .label {{ font-size:0.8rem; color:#94a3b8; }}
  table {{ width:100%; border-collapse:collapse; margin-top:1rem; }}
  th, td {{ text-align:left; padding:0.6rem 0.8rem; border-bottom:1px solid #1e293b; font-size:0.85rem; }}
  th {{ color:#94a3b8; cursor:pointer; }}
  tr:hover td {{ background:#1e293b; }}
  code {{ font-family:'JetBrains Mono',monospace; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:999px; color:#fff; font-size:0.75rem; font-weight:600; }}
  .bar {{ height:4px; background:#3b82f6; border-radius:2px; margin-top:4px; }}
  .green {{ color:#22c55e; }} .red {{ color:#ef4444; }}
</style></head>
<body>
<h1>🤖 ReformBoss <span style="font-size:0.9rem;color:#94a3b8;">live</span></h1>
<div class="stats">
  <div class="stat-card"><div class="num" style="color:#3b82f6;">{len(metrics)}</div><div class="label">Моделей</div></div>
  <div class="stat-card"><div class="num green">{sum(1 for m in metrics if model_status(metrics,m)=='stable')}</div><div class="label">Stable</div></div>
  <div class="stat-card"><div class="num" style="color:#eab308;">{sum(1 for m in metrics if model_status(metrics,m)=='unstable')}</div><div class="label">Unstable</div></div>
  <div class="stat-card"><div class="num red">{sum(1 for m in metrics if model_status(metrics,m)=='dead')}</div><div class="label">Dead</div></div>
  <div class="stat-card"><div class="num" style="color:{'#22c55e' if hs>=70 else '#eab308'}">{hs}</div><div class="label">Health Score</div></div>
</div>
<table><thead><tr><th>Модель</th><th>Статус</th><th>Success</th><th>TTFT</th><th>Проверки</th><th>Появилась</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<div style="margin-top:1rem;font-size:0.8rem;color:#64748b;">
  Обновлено {datetime.now().strftime('%d.%m.%Y %H:%M')} ·
  <a href="/api/metrics" style="color:#3b82f6;">JSON API</a> ·
  <a href="/health" style="color:#3b82f6;">Health</a>
</div>
<script>
  document.querySelectorAll('th').forEach((th,i) => th.addEventListener('click',()=>{{
    const tbody=document.querySelector('tbody'),rows=Array.from(tbody.querySelectorAll('tr'));
    const dir=th.classList.toggle('asc')?1:-1;
    rows.sort((a,b)=>{{const ca=a.cells[i].textContent.trim(),cb=b.cells[i].textContent.trim();
    const na=parseFloat(ca),nb=parseFloat(cb);return (isNaN(na)||isNaN(nb)?ca.localeCompare(cb):na-nb)*dir;}});
    rows.forEach(r=>tbody.appendChild(r));
  }}));
</script></body></html>"""
        self.wfile.write(html.encode())


def serve(host="0.0.0.0", port=9090):
    """Запустить HTTP-дашборд."""
    server = HTTPServer((host, port), DashboardHandler)
    print(f"  🌐 Дашборд: http://{host}:{port}")
    print(f"  📡 API:     http://{host}:{port}/api/metrics")
    print(f"  ❤️  Health:  http://{host}:{port}/health")
    print(f"  {dim('Ctrl+C для выхода')}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  сервер остановлен")
        server.server_close()


def dim(t):
    return f"\033[2m{t}\033[0m"
