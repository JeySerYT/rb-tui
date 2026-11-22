"""HTTP-дашборд: --serve"""

import json
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

from rb_tui import __version__
from rb_tui.dashboard_view import build_view, build_model_detail
from rb_tui.metrics import (
    load_metrics, load_history, full_stats, health_score,
)
from rb_tui.export import export_csv, export_json
from rb_tui.sync import load_catalog_owned
from rb_tui.utils import load_tags, y

STARTED_AT = time.time()


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP-сервер: HTML-панель и JSON для автообновления."""

    def _send(self, code, body, content_type, extra_headers=None):
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")

    def _send_download(self, filename, content_type, body):
        self._send(200, body, content_type, {
            "Content-Disposition": f'attachment; filename="{filename}"',
        })

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            metrics = load_metrics()
            self._send_json({
                "status": "ok",
                "version": __version__,
                "uptime_seconds": round(time.time() - STARTED_AT),
                "health_score": health_score(metrics),
                "models": len(metrics),
                "timestamp": datetime.now().isoformat(),
            })
            return

        if path == "/api/view":
            self._send_json(build_view(
                load_metrics(), load_catalog_owned(), load_tags(),
            ))
            return

        if path.startswith("/api/model/"):
            model_id = unquote(path[len("/api/model/"):])
            metrics = load_metrics()
            detail = build_model_detail(
                metrics, model_id, load_history(model_id, limit=40),
            )
            if detail is None:
                self._send_json({"error": "not found"}, code=404)
            else:
                self._send_json(detail)
            return

        if path == "/api/metrics":
            metrics = load_metrics()
            data = {}
            for mid in metrics:
                stats = full_stats(metrics, mid)
                if stats:
                    data[mid] = stats
            self._send_json(data)
            return

        if path == "/export.csv":
            self._send_download(
                "rb-tui-metrics.csv", "text/csv; charset=utf-8", export_csv(),
            )
            return

        if path == "/export.json":
            self._send_download(
                "rb-tui-metrics.json", "application/json; charset=utf-8", export_json(),
            )
            return

        if path in ("/", "/index.html"):
            view = build_view(load_metrics(), load_catalog_owned(), load_tags())
            self._send(200, render_html(view), "text/html; charset=utf-8")
            return

        self._send_json({"error": "not found"}, code=404)

    def log_message(self, fmt, *args):
        # Не засоряем терминал каждой загрузкой страницы.
        return


def render_html(view):
    initial = (
        json.dumps(view, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return HTML.replace("__INITIAL__", initial)


HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="dark">
<title>ReformBoss — мониторинг моделей</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%230e1012'/%3E%3Ctext x='16' y='21' font-family='monospace' font-size='12' fill='%23d6f264' text-anchor='middle'%3Erb%3C/text%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{
    color-scheme: dark;
    --bg:#08090a;
    --surface:#0e1012;
    --surface-2:#13171a;
    --line:#1e2328;
    --line-strong:#2b3238;
    --text:#e9ecef;
    --muted:#8f98a3;
    --accent:#d6f264;
    --ok:#5ecf87;
    --warn:#e0b341;
    --bad:#e5675f;
    --radius:14px;
    --font:"Geist", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    --mono:"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{
    margin:0;
    min-height:100vh;
    background:var(--bg);
    color:var(--text);
    font-family:var(--font);
    font-size:15px;
    line-height:1.45;
    -webkit-font-smoothing:antialiased;
  }
  a{color:var(--accent);text-decoration:none}
  a:hover{text-decoration:underline}
  :focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
  .sr-only{
    position:absolute;width:1px;height:1px;padding:0;margin:-1px;
    overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;
  }
  .skip{
    position:absolute;left:12px;top:-60px;z-index:10;
    background:var(--accent);color:#0a0b09;padding:8px 14px;border-radius:8px;
    font-weight:600;transition:top .15s ease;
  }
  .skip:focus{top:12px}
  .wrap{max-width:1280px;margin:0 auto;padding:28px 24px 40px}
  header.top{
    display:flex;align-items:center;justify-content:space-between;
    gap:20px;flex-wrap:wrap;margin-bottom:26px;
  }
  .brand{display:flex;align-items:center;gap:12px}
  .mark{
    display:grid;place-items:center;width:38px;height:38px;border-radius:11px;
    border:1px solid var(--line-strong);background:var(--surface);
    color:var(--accent);font-family:var(--mono);font-size:.82rem;font-weight:500;
    letter-spacing:-.04em;
  }
  h1{font-size:1.06rem;font-weight:600;letter-spacing:-.01em;margin:0}
  .sub{
    margin:1px 0 0;font-size:.7rem;letter-spacing:.13em;text-transform:uppercase;
    color:var(--muted);
  }
  .top-right{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
  .live{
    display:inline-flex;align-items:center;gap:7px;
    font-family:var(--mono);font-size:.72rem;letter-spacing:.06em;
    text-transform:uppercase;color:var(--muted);
  }
  .live .dot{
    width:7px;height:7px;border-radius:50%;background:var(--ok);
    box-shadow:0 0 0 3px rgba(94,207,135,.14);
    animation:pulse 2.4s ease-in-out infinite;
  }
  .live.offline .dot{background:var(--bad);box-shadow:0 0 0 3px rgba(229,103,95,.14);animation:none}
  @keyframes pulse{50%{opacity:.45}}
  .updated{font-family:var(--mono);font-size:.72rem;color:var(--muted)}
  .btn{
    appearance:none;font:inherit;font-size:.8rem;font-weight:500;
    color:var(--text);background:var(--surface);
    border:1px solid var(--line-strong);border-radius:10px;
    padding:8px 14px;cursor:pointer;
    transition:border-color .15s ease,background .15s ease;
  }
  .btn:hover{border-color:var(--muted);background:var(--surface-2)}
  .btn:disabled{opacity:.5;cursor:progress}

  .kpis{
    display:grid;grid-template-columns:repeat(4,minmax(0,1fr));
    gap:10px;margin:0 0 22px;padding:0;
  }
  .kpi{
    background:var(--surface);border:1px solid var(--line);
    border-radius:var(--radius);padding:14px 16px;
  }
  .kpi dt{
    font-size:.7rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
  }
  .kpi dd{
    margin:7px 0 0;font-family:var(--mono);font-size:1.45rem;font-weight:500;
    line-height:1.1;font-variant-numeric:tabular-nums;letter-spacing:-.02em;
  }
  .kpi dd .unit{font-size:.72rem;color:var(--muted);letter-spacing:0;margin-left:3px}
  .kpi--health dd{color:var(--accent)}
  .kpi--ok dd{color:var(--ok)}
  .kpi--warn dd{color:var(--warn)}
  .kpi--bad dd{color:var(--bad)}

  .panel{
    background:var(--surface);border:1px solid var(--line);
    border-radius:var(--radius);overflow:hidden;
  }
  .panel-head{
    display:flex;align-items:baseline;justify-content:space-between;gap:12px;
    padding:16px 18px 0;
  }
  .panel-head h2{font-size:.95rem;font-weight:600;margin:0;letter-spacing:-.01em}
  .count{font-family:var(--mono);font-size:.72rem;color:var(--muted)}
  .toolbar{
    display:flex;align-items:center;justify-content:space-between;gap:14px;
    flex-wrap:wrap;padding:14px 18px 16px;
  }
  .search input{
    width:min(320px,76vw);font:inherit;font-size:.82rem;
    color:var(--text);background:var(--bg);
    border:1px solid var(--line-strong);border-radius:10px;
    padding:9px 12px;
  }
  .search input::placeholder{color:var(--muted)}
  .chips{display:flex;gap:6px;flex-wrap:wrap}
  .chip{
    appearance:none;font:inherit;font-size:.76rem;font-weight:500;
    color:var(--muted);background:transparent;
    border:1px solid var(--line);border-radius:999px;
    padding:6px 11px;cursor:pointer;
    transition:color .15s ease,border-color .15s ease,background .15s ease;
  }
  .chip:hover{color:var(--text);border-color:var(--line-strong)}
  .chip[aria-pressed="true"]{
    color:var(--accent);border-color:rgba(214,242,100,.55);
    background:rgba(214,242,100,.08);
  }
  .chip .n{font-family:var(--mono);opacity:.7;margin-left:4px}
  .selects{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
  .selects select{
    font:inherit;font-size:.76rem;color:var(--text);background:var(--bg);
    border:1px solid var(--line-strong);border-radius:9px;padding:7px 9px;
    max-width:180px;
  }
  .selects label{font-size:.72rem;color:var(--muted)}
  .export{display:flex;gap:8px;flex-wrap:wrap}
  .btn--sm{padding:6px 10px;font-size:.74rem}

  .table-wrap{max-height:min(62vh,640px);overflow:auto}
  table{width:100%;border-collapse:collapse;font-size:.83rem}
  caption{caption-side:top}
  thead th{
    position:sticky;top:0;z-index:2;padding:0;
    background:var(--surface);border-top:1px solid var(--line);
    border-bottom:1px solid var(--line-strong);text-align:left;
  }
  thead th button{
    appearance:none;width:100%;font:inherit;font-size:.7rem;font-weight:500;
    letter-spacing:.08em;text-transform:uppercase;color:var(--muted);
    background:transparent;border:0;padding:11px 14px;cursor:pointer;
    text-align:left;white-space:nowrap;
  }
  thead th button:hover{color:var(--text)}
  .th-unit{
    text-transform:none;letter-spacing:0;font-weight:400;
    opacity:.65;margin-left:2px;
  }
  th.num button{text-align:right}
  th[aria-sort="ascending"] button,
  th[aria-sort="descending"] button{color:var(--accent)}
  th[aria-sort="ascending"] button::after{content:" ↑"}
  th[aria-sort="descending"] button::after{content:" ↓"}
  tbody td{
    padding:10px 14px;border-bottom:1px solid var(--line);
    white-space:nowrap;vertical-align:middle;
  }
  tbody tr:last-child td{border-bottom:0}
  tbody tr:hover td{background:var(--surface-2)}
  .num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
  .model{
    font-family:var(--mono);font-size:.79rem;color:var(--text);
    display:inline-block;max-width:360px;overflow:hidden;
    text-overflow:ellipsis;vertical-align:bottom;
  }
  .model-link{
    appearance:none;border:0;background:transparent;padding:0;margin:0;
    font:inherit;color:inherit;cursor:pointer;text-align:left;
    display:inline-flex;align-items:center;gap:6px;max-width:380px;
  }
  .model-link:hover{color:var(--accent)}
  .model-link code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .flag{font-size:.72rem;line-height:1}
  .flag.err{color:var(--bad)}
  .flag.fp{color:var(--warn)}
  .tag{font-family:var(--mono);font-size:.66rem;color:var(--muted);
    border:1px solid var(--line);border-radius:999px;padding:1px 7px}
  .when{font-family:var(--mono);font-size:.74rem;color:var(--muted)}
  .muted{color:var(--muted)}
  .v-ok{color:var(--ok)}
  .v-warn{color:var(--warn)}
  .v-bad{color:var(--bad)}
  .badge{
    display:inline-flex;align-items:center;gap:6px;
    font-size:.7rem;font-weight:600;letter-spacing:.02em;
    padding:3px 9px;border-radius:999px;border:1px solid;
  }
  .badge::before{content:"";width:5px;height:5px;border-radius:50%;background:currentColor}
  .badge.stable{color:var(--ok);border-color:rgba(94,207,135,.35);background:rgba(94,207,135,.1)}
  .badge.unstable{color:var(--warn);border-color:rgba(224,179,65,.35);background:rgba(224,179,65,.1)}
  .badge.dead{color:var(--bad);border-color:rgba(229,103,95,.35);background:rgba(229,103,95,.1)}
  .badge.unknown{color:var(--muted);border-color:var(--line-strong);background:rgba(143,152,163,.08)}
  .empty{
    padding:40px 24px 48px;text-align:center;color:var(--muted);font-size:.86rem;
  }
  .empty strong{display:block;color:var(--text);font-weight:500;margin-bottom:6px}
  .note{padding:0 18px 16px;font-size:.74rem;color:var(--muted);min-height:1em}
  .note.err{color:var(--bad)}
  footer{
    display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;
    margin-top:20px;font-size:.74rem;color:var(--muted);
  }
  footer .links{display:flex;gap:14px}

  .backdrop{
    position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:20;
    opacity:0;transition:opacity .16s ease;
  }
  .backdrop[hidden]{display:none}
  .backdrop.open{opacity:1}
  .drawer{
    position:fixed;top:0;right:0;bottom:0;width:min(560px,94vw);z-index:21;
    background:var(--surface);border-left:1px solid var(--line-strong);
    transform:translateX(102%);transition:transform .18s ease;
    display:flex;flex-direction:column;
  }
  .drawer.open{transform:none}
  .drawer-head{
    display:flex;align-items:center;justify-content:space-between;gap:12px;
    padding:18px 20px;border-bottom:1px solid var(--line);
  }
  .drawer-head h2{font-size:.95rem;margin:0;font-family:var(--mono);overflow:hidden;text-overflow:ellipsis}
  .drawer-body{padding:18px 20px 28px;overflow:auto}
  .detail-kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0 0 18px}
  .detail-kpis div{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:9px 11px}
  .detail-kpis dt{font-size:.64rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
  .detail-kpis dd{margin:4px 0 0;font-family:var(--mono);font-size:1rem}
  .chart-row{display:grid;grid-template-columns:52px 1fr;gap:10px;align-items:center;margin:0 0 12px}
  .chart-row .label{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
  .chart-row svg{width:100%;height:44px;display:block}
  .detail-table{width:100%;border-collapse:collapse;font-size:.74rem;margin-top:6px}
  .detail-table th{position:static;padding:6px 8px;border-bottom:1px solid var(--line-strong);color:var(--muted);text-align:left;font-weight:500}
  .detail-table td{padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
  .detail-table td.msg{max-width:170px;overflow:hidden;text-overflow:ellipsis;color:var(--bad)}
  .detail-empty{color:var(--muted);font-size:.8rem;padding:10px 0}
  body.locked{overflow:hidden}

  @media (max-width:900px){
    .kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  }
  @media (max-width:640px){
    .wrap{padding:20px 14px 32px}
    .model{max-width:220px}
  }
  @media (prefers-reduced-motion: reduce){
    *{animation:none !important;transition:none !important}
  }
</style>
</head>
<body>
<a class="skip" href="#models">Перейти к таблице</a>
<div class="wrap">
  <header class="top">
    <div class="brand">
      <span class="mark" aria-hidden="true">rb</span>
      <div>
        <h1>ReformBoss</h1>
        <p class="sub">Мониторинг моделей</p>
      </div>
    </div>
    <div class="top-right">
      <span class="live" id="live"><span class="dot" aria-hidden="true"></span>live</span>
      <span class="updated" id="updated">—</span>
      <button class="btn" id="refresh" type="button">Обновить</button>
    </div>
  </header>

  <main>
    <dl class="kpis" aria-label="Ключевые показатели">
      <div class="kpi"><dt>Моделей</dt><dd id="kpi-models">—</dd></div>
      <div class="kpi kpi--health"><dt>Health</dt><dd id="kpi-health">—</dd></div>
      <div class="kpi kpi--ok"><dt>Stable</dt><dd id="kpi-stable">—</dd></div>
      <div class="kpi kpi--warn"><dt>Unstable</dt><dd id="kpi-unstable">—</dd></div>
      <div class="kpi kpi--bad"><dt>Dead</dt><dd id="kpi-dead">—</dd></div>
      <div class="kpi"><dt>Ср. TTFT</dt><dd id="kpi-ttft">—</dd></div>
      <div class="kpi"><dt>Ср. TTS</dt><dd id="kpi-tts">—</dd></div>
      <div class="kpi"><dt>Ср. TPS</dt><dd id="kpi-tps">—</dd></div>
    </dl>

    <section class="panel" aria-labelledby="models-title">
      <div class="panel-head">
        <h2 id="models-title">Модели</h2>
        <span class="count" id="count">—</span>
      </div>
      <div class="toolbar">
        <div class="search">
          <label class="sr-only" for="q">Поиск по названию модели</label>
          <input id="q" type="search" placeholder="Поиск модели…" autocomplete="off" spellcheck="false">
        </div>
        <div class="selects">
          <label for="owner">Провайдер</label>
          <select id="owner"><option value="">все</option></select>
          <label for="tag">Тег</label>
          <select id="tag"><option value="">все</option></select>
        </div>
        <div class="chips" role="group" aria-label="Фильтр по статусу">
          <button class="chip" type="button" data-status="all" aria-pressed="true">Все <span class="n" id="n-all">0</span></button>
          <button class="chip" type="button" data-status="stable" aria-pressed="false">Stable <span class="n" id="n-stable">0</span></button>
          <button class="chip" type="button" data-status="unstable" aria-pressed="false">Unstable <span class="n" id="n-unstable">0</span></button>
          <button class="chip" type="button" data-status="dead" aria-pressed="false">Dead <span class="n" id="n-dead">0</span></button>
        </div>
        <div class="export">
          <a class="btn btn--sm" href="/export.csv" download>CSV</a>
          <a class="btn btn--sm" href="/export.json" download>JSON</a>
        </div>
      </div>
      <div class="table-wrap">
        <table id="models">
          <caption class="sr-only">Модели: статус, доля успешных проб, задержки TTFT и TTS, скорость TPS, число проверок.</caption>
          <thead>
            <tr>
              <th scope="col" aria-sort="none"><button type="button" data-sort="id" title="Идентификатор модели">Модель</button></th>
              <th scope="col" aria-sort="ascending"><button type="button" data-sort="status" title="Статус по последним проверкам">Статус</button></th>
              <th scope="col" class="num" aria-sort="none"><button type="button" data-sort="success_rate" title="Доля успешных проверок">Success</button></th>
              <th scope="col" class="num" aria-sort="none"><button type="button" data-sort="avg_ttft" title="Время до первого токена">TTFT <span class="th-unit">s</span></button></th>
              <th scope="col" class="num" aria-sort="none"><button type="button" data-sort="avg_tts" title="Время до второго токена">TTS <span class="th-unit">s</span></button></th>
              <th scope="col" class="num" aria-sort="none"><button type="button" data-sort="avg_tps" title="Эффективная скорость: токенов в секунду за всё время ответа">TPS <span class="th-unit">tok/s</span></button></th>
              <th scope="col" class="num" aria-sort="none"><button type="button" data-sort="total" title="Всего проверок и успешных">Проверки</button></th>
              <th scope="col" aria-sort="none"><button type="button" data-sort="last_seen" title="Время последней проверки">Последний</button></th>
            </tr>
          </thead>
          <tbody id="rows"></tbody>
        </table>
        <div class="empty" id="empty" hidden></div>
      </div>
      <p class="note" id="note" aria-live="polite"></p>
    </section>
  </main>

  <div class="backdrop" id="backdrop" hidden></div>
  <aside class="drawer" id="drawer" aria-hidden="true" aria-labelledby="drawer-title">
    <div class="drawer-head">
      <h2 id="drawer-title">Модель</h2>
      <button class="btn btn--sm" id="drawer-close" type="button">Закрыть</button>
    </div>
    <div class="drawer-body" id="drawer-body"></div>
  </aside>

  <footer>
    <span>rb-tui · автообновление каждые 30 с</span>
    <span class="links">
      <a href="/api/view">JSON /api/view</a>
      <a href="/health">health</a>
    </span>
  </footer>
</div>

<script>
(() => {
  "use strict";

  const INITIAL = __INITIAL__;
  const STATUS_ORDER = {stable: 0, unstable: 1, dead: 2, unknown: 3};
  const state = {
    view: INITIAL,
    query: "",
    status: "all",
    owner: "",
    tag: "",
    sort: {key: "status", dir: 1},
  };

  const $ = (id) => document.getElementById(id);
  const rowsEl = $("rows");
  const emptyEl = $("empty");
  const noteEl = $("note");
  const liveEl = $("live");
  const refreshEl = $("refresh");
  const ownerEl = $("owner");
  const tagEl = $("tag");
  const drawerEl = $("drawer");
  const drawerBody = $("drawer-body");
  const drawerTitle = $("drawer-title");
  const backdropEl = $("backdrop");
  const closeEl = $("drawer-close");

  function esc(value) {
    return String(value).replace(/[&<>"']/g, (c) => (
      {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]
    ));
  }

  function num(value, digits) {
    if (value === null || value === undefined) return "—";
    return Number(value).toLocaleString("ru-RU", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function unit(value, suffix) {
    return value === null || value === undefined
      ? '<span class="muted">—</span>'
      : num(value, suffix === " tok/s" ? 1 : 3) + `<span class="unit">${suffix}</span>`;
  }

  function level(value, ok, warn) {
    if (value === null || value === undefined) return "muted";
    if (value >= ok) return "v-ok";
    if (value >= warn) return "v-warn";
    return "v-bad";
  }

  function delayLevel(value) {
    if (value === null || value === undefined) return "muted";
    if (value < 2) return "v-ok";
    if (value < 5) return "v-warn";
    return "v-bad";
  }

  function fmt(value, digits, suffix) {
    return value === null || value === undefined
      ? "—"
      : num(value, digits) + (suffix || "");
  }

  function fillSelect(el, values, current) {
    const keep = values.includes(current) ? current : "";
    el.innerHTML = '<option value="">все</option>' + values
      .map((v) => `<option value="${esc(v)}">${esc(v)}</option>`)
      .join("");
    el.value = keep;
    return keep;
  }

  function renderFilterOptions() {
    const models = state.view.models || [];
    const owners = [...new Set(models.map((m) => m.owner).filter(Boolean))].sort();
    const tags = [...new Set(models.map((m) => m.tag).filter(Boolean))].sort();
    state.owner = fillSelect(ownerEl, owners, state.owner);
    state.tag = fillSelect(tagEl, tags, state.tag);
  }

  function renderKpis(v) {
    const c = v.counts || {};
    const a = v.averages || {};
    $("kpi-models").textContent = v.models.length;
    $("kpi-health").textContent = v.health;
    $("kpi-stable").textContent = c.stable || 0;
    $("kpi-unstable").textContent = c.unstable || 0;
    $("kpi-dead").textContent = c.dead || 0;
    $("kpi-ttft").innerHTML = unit(a.ttft, " s");
    $("kpi-tts").innerHTML = unit(a.tts, " s");
    $("kpi-tps").innerHTML = unit(a.tps, " tok/s");
    $("n-all").textContent = v.models.length;
    $("n-stable").textContent = c.stable || 0;
    $("n-unstable").textContent = c.unstable || 0;
    $("n-dead").textContent = c.dead || 0;
    const fp = v.fp_changed || 0;
    $("updated").textContent = "данные на " + v.generated_at
      + (fp ? ` · fingerprint ⚠ ${fp}` : "");
  }

  function visibleRows() {
    const q = state.query.trim().toLowerCase();
    const rows = state.view.models.filter((m) => {
      if (state.status !== "all" && m.status !== state.status) return false;
      if (state.owner && m.owner !== state.owner) return false;
      if (state.tag && m.tag !== state.tag) return false;
      return !q || m.id.toLowerCase().includes(q);
    });

    const {key, dir} = state.sort;
    rows.sort((a, b) => {
      if (key === "status") {
        const d = (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9);
        if (d !== 0) return d * dir;
        if (a.avg_ttft === null || a.avg_ttft === undefined) return 1;
        if (b.avg_ttft === null || b.avg_ttft === undefined) return -1;
        return ((a.avg_ttft - b.avg_ttft) * dir) || a.id.localeCompare(b.id);
      }
      if (key === "id" || key === "last_seen") {
        return String(a[key]).localeCompare(String(b[key])) * dir;
      }
      const av = a[key];
      const bv = b[key];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      return (av - bv) * dir;
    });
    return rows;
  }

  function rowHtml(m) {
    const flags =
      (m.last_error ? `<span class="flag err" title="Последняя ошибка: ${esc(m.last_error)}">⚠</span>` : "")
      + (m.fp_changed ? '<span class="flag fp" title="fingerprint менялся: модель могли подменить">◆</span>' : "");
    const tag = m.tag ? `<span class="tag">${esc(m.tag)}</span>` : "";
    return `<tr>
      <td><button class="model-link" type="button" data-model="${esc(m.id)}" title="Открыть карточку модели">
        <code>${esc(m.id)}</code>${flags}${tag}
      </button></td>
      <td><span class="badge ${esc(m.status)}">${esc(m.status)}</span></td>
      <td class="num ${level(m.success_rate, 80, 30)}">${m.success_rate}%</td>
      <td class="num ${delayLevel(m.avg_ttft)}">${num(m.avg_ttft, 3)}</td>
      <td class="num ${delayLevel(m.avg_tts)}">${num(m.avg_tts, 3)}</td>
      <td class="num ${level(m.avg_tps, 15, 5)}">${num(m.avg_tps, 1)}</td>
      <td class="num">${m.total}<span class="muted"> · ${m.ok} ok</span></td>
      <td class="when">${esc(m.last_seen)}</td>
    </tr>`;
  }

  function sparkline(values, color) {
    const points = [];
    let lo = Infinity, hi = -Infinity;
    values.forEach((v) => {
      if (v === null || v === undefined) return;
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    });
    if (!Number.isFinite(lo)) return '<div class="detail-empty">нет данных</div>';
    const w = 260, h = 40, pad = 4, span = hi - lo || 1;
    values.forEach((v, i) => {
      if (v === null || v === undefined) return;
      points.push([
        pad + i * (w - pad * 2) / Math.max(1, values.length - 1),
        h - pad - (v - lo) / span * (h - pad * 2),
      ]);
    });
    if (points.length < 2) return '<div class="detail-empty">мало данных для графика</div>';
    const d = points.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="график">
      <path d="${d}" fill="none" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>
    </svg>`;
  }

  function openDrawer() {
    backdropEl.hidden = false;
    requestAnimationFrame(() => {
      backdropEl.classList.add("open");
      drawerEl.classList.add("open");
    });
    drawerEl.setAttribute("aria-hidden", "false");
    document.body.classList.add("locked");
    closeEl.focus();
  }

  function closeDrawer() {
    drawerEl.classList.remove("open");
    backdropEl.classList.remove("open");
    drawerEl.setAttribute("aria-hidden", "true");
    document.body.classList.remove("locked");
    setTimeout(() => { backdropEl.hidden = true; }, 180);
  }

  function renderDetail(data) {
    const s = data.stats || {};
    const hist = data.history || [];
    const fp = s.fp_changed;
    const rows = hist.slice().reverse().slice(0, 12).map((e) => `<tr>
      <td class="when">${esc(e.ts || "")}</td>
      <td class="${e.status === "OK" ? "v-ok" : "v-bad"}">${esc(e.status || "")}</td>
      <td class="num">${fmt(e.ttft, 3)}</td>
      <td class="num">${fmt(e.tts, 3)}</td>
      <td class="num">${fmt(e.tps, 1)}</td>
      <td class="msg" title="${esc(e.msg || "")}">${esc(e.msg || "")}</td>
    </tr>`).join("");

    drawerBody.innerHTML = `
      <dl class="detail-kpis">
        <div><dt>Статус</dt><dd class="${s.status === "stable" ? "v-ok" : (s.status === "dead" ? "v-bad" : "v-warn")}">${esc(s.status || "—")}</dd></div>
        <div><dt>Success</dt><dd>${s.success_rate != null ? s.success_rate + "%" : "—"}</dd></div>
        <div><dt>Проверок</dt><dd>${s.total ?? "—"}</dd></div>
        <div><dt>Ср. TTFT</dt><dd>${fmt(s.avg_ttft, 3, "s")}</dd></div>
        <div><dt>Ср. TTS</dt><dd>${fmt(s.avg_tts, 3, "s")}</dd></div>
        <div><dt>Ср. TPS</dt><dd>${fmt(s.avg_tps, 1)}</dd></div>
      </dl>
      <div class="chart-row"><span class="label">TTFT</span>${sparkline(hist.map((e) => e.ttft), "#e9ecef")}</div>
      <div class="chart-row"><span class="label">TTS</span>${sparkline(hist.map((e) => e.tts), "#8f98a3")}</div>
      <div class="chart-row"><span class="label">TPS</span>${sparkline(hist.map((e) => e.tps), "#d6f264")}</div>
      ${fp ? `<p class="note err">fingerprint сменился: ${esc(fp.from || "")} → ${esc(fp.to || "")}</p>` : ""}
      ${s.last_error ? `<p class="note err">последняя ошибка: ${esc(s.last_error)}</p>` : ""}
      <table class="detail-table">
        <thead><tr><th>Когда</th><th>Статус</th><th>TTFT</th><th>TTS</th><th>TPS</th><th>Ошибка</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="6" class="detail-empty">проб ещё нет</td></tr>'}</tbody>
      </table>`;
  }

  async function openModel(modelId) {
    drawerTitle.textContent = modelId;
    drawerBody.innerHTML = '<div class="detail-empty">загружаю историю…</div>';
    openDrawer();
    try {
      const res = await fetch("/api/model/" + encodeURIComponent(modelId), {cache: "no-store"});
      if (!res.ok) throw new Error("HTTP " + res.status);
      renderDetail(await res.json());
    } catch (err) {
      drawerBody.innerHTML = `<div class="detail-empty v-bad">не удалось загрузить модель: ${esc(err.message)}</div>`;
    }
  }

  function render() {
    const v = state.view;
    renderKpis(v);

    const rows = visibleRows();
    rowsEl.innerHTML = rows.map(rowHtml).join("");
    $("count").textContent = rows.length === v.models.length
      ? `${v.models.length} моделей`
      : `${rows.length} из ${v.models.length}`;

    if (rows.length === 0) {
      emptyEl.hidden = false;
      if (v.models.length === 0) {
        emptyEl.innerHTML = "<strong>Пока нет данных</strong>Запусти <code>rb-tui --sync</code> или <code>rb-tui --test</code>, чтобы собрать первые метрики.";
      } else {
        emptyEl.innerHTML = "<strong>Ничего не найдено</strong>Измени поиск или сбрось фильтры.";
      }
    } else {
      emptyEl.hidden = true;
    }

    document.querySelectorAll("th[aria-sort]").forEach((th) => {
      const button = th.querySelector("button[data-sort]");
      if (!button) return;
      if (button.dataset.sort === state.sort.key) {
        th.setAttribute("aria-sort", state.sort.dir === 1 ? "ascending" : "descending");
      } else {
        th.setAttribute("aria-sort", "none");
      }
    });
  }

  async function refresh() {
    refreshEl.disabled = true;
    try {
      const res = await fetch("/api/view", {cache: "no-store"});
      if (!res.ok) throw new Error("HTTP " + res.status);
      state.view = await res.json();
      renderFilterOptions();
      render();
      liveEl.classList.remove("offline");
      noteEl.classList.remove("err");
      noteEl.textContent = "обновлено " + new Date().toLocaleTimeString("ru-RU");
    } catch (err) {
      liveEl.classList.add("offline");
      noteEl.classList.add("err");
      noteEl.textContent = "нет связи с сервером: " + err.message;
    } finally {
      refreshEl.disabled = false;
    }
  }

  $("q").addEventListener("input", (e) => {
    state.query = e.target.value;
    render();
  });

  ownerEl.addEventListener("change", (e) => {
    state.owner = e.target.value;
    render();
  });

  tagEl.addEventListener("change", (e) => {
    state.tag = e.target.value;
    render();
  });

  rowsEl.addEventListener("click", (e) => {
    const button = e.target.closest("[data-model]");
    if (button) openModel(button.dataset.model);
  });

  closeEl.addEventListener("click", closeDrawer);
  backdropEl.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawerEl.classList.contains("open")) closeDrawer();
  });

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.status = chip.dataset.status;
      document.querySelectorAll(".chip").forEach((c) => {
        c.setAttribute("aria-pressed", String(c === chip));
      });
      render();
    });
  });

  document.querySelectorAll("th button[data-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.sort;
      if (state.sort.key === key) {
        state.sort.dir *= -1;
      } else {
        state.sort = {key, dir: 1};
      }
      render();
    });
  });

  refreshEl.addEventListener("click", refresh);

  setInterval(() => {
    if (!document.hidden) refresh();
  }, 30000);

  renderFilterOptions();
  render();
  noteEl.textContent = "данные на " + state.view.generated_at;
})();
</script>
</body>
</html>
"""


def serve(host="127.0.0.1", port=9090):
    """Запустить HTTP-дашборд."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(y(f"  ⚠ {host} — дашборд без авторизации будет доступен по сети"))
        print(y("    для локальной работы оставь --serve-host 127.0.0.1"))
    try:
        server = ThreadingHTTPServer((host, port), DashboardHandler)
    except OSError as e:
        print(f"  ❌ не смог занять {host}:{port} — {e}")
        print("  порт занят? укажи другой: rb-tui --serve --serve-port 9091")
        return
    print(f"  🌐 Дашборд: http://{host}:{port}")
    print(f"  📡 API:     http://{host}:{port}/api/view")
    print(f"  ❤️  Health:  http://{host}:{port}/health")
    print(f"  {dim('Ctrl+C для выхода')}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  сервер остановлен")
        server.server_close()


def dim(t):
    return f"\033[2m{t}\033[0m"