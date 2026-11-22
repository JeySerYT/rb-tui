"""Вывод в терминал: таблицы, топ, статистика, отчёты."""

from datetime import datetime

from rb_tui.utils import (
    g, r, y, bl, cy, dim, bold,
)
from rb_tui.metrics import (
    model_status, avg_ttft, avg_tts, avg_tps, success_rate, full_stats,
    health_score, find_anomalies, lifetime,
)
from rb_tui.api import fetch_catalog
from rb_tui.probe import probe_with_metrics


def render_report(cfg_models, live, new, gone, key_ok, base, prev_date, appeared, disappeared):
    print()
    print(dim("╭" + "─" * 54 + "╮"))
    print(dim("│") + bold("  REFORMBOSS · сверка каталога и конфига") + " " * 13 + dim("│"))
    print(dim("╰" + "─" * 54 + "╯"))
    print(f"  {dim('каталог:')} {len(live):>3} моделей   {dim('конфиг:')} {len(cfg_models):>3} моделей")
    print(f"  {dim('api:')} {base}   {dim('ключ:')} {'ok' if key_ok else r('НЕ НАЙДЕН')}")
    print()
    if prev_date is None:
        print(dim("  первая проверка: база для отслеживания изменений создана"))
    elif appeared or disappeared:
        print(bold(f"  ИЗМЕНЕНИЯ КАТАЛОГА с прошлой проверки ({prev_date})"))
        for m in appeared:
            print(f"    {g('+')} {m}  {dim('(появилась)')}")
        for m in disappeared:
            print(f"    {r('-')} {m}  {dim('(исчезла)')}")
        print()
    else:
        print(dim(f"  с прошлой проверки ({prev_date}) каталог не изменился"))
    if new:
        print(g(f"  НОВЫЕ в каталоге, нет в конфиге ({len(new)})"))
        for m in new:
            print(f"    {g('+')} {m}")
    else:
        print(dim("  новых нет"))
    print()
    if gone:
        print(r(f"  ПРОПАВШИЕ из каталога, есть в конфиге ({len(gone)})"))
        for m in gone:
            print(f"    {r('-')} {m}")
    else:
        print(dim("  пропавших нет"))
    print()


def _secs(value):
    if value is None:
        return ""
    col = g if value < 2 else (y if value < 5 else r)
    return col(f"{value:.3f}")


def _clock(ts):
    """HH:MM из метки времени со смещением или из старого локального формата."""
    try:
        return datetime.fromisoformat(ts).strftime("%H:%M")
    except (ValueError, TypeError):
        return str(ts)[-5:]


def print_test_table(results, metrics=None):
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()
    print(bold(f"  ТЕСТ ДОСТУПНОСТИ ({len(results)} моделей)"))
    print(f"  {'Модель':<34} {'TTFT':<7} {'TTS':<7} {'TPS':<7} {'Ср.TTFT':<8} {'Статус':<9} {'%/N':<7} {'Ошибка'}")
    print(dim("  " + "─" * 102))
    for mid, status, ttft, tts, total, tokens, fp, msg in results:
        st = model_status(metrics, mid) if metrics else "?"
        avg_t = avg_ttft(metrics, mid) if metrics else None
        rate = success_rate(metrics, mid) if metrics else None

        s_badge = ""
        if st == "stable":
            s_badge = g("stable")
        elif st == "unstable":
            s_badge = y("unstable")
        elif st == "dead":
            s_badge = r("dead")
        else:
            s_badge = dim("?")

        rate_str = ""
        if rate is not None:
            col = g if rate >= 80 else (y if rate >= 30 else r)
            rate_str = col(f"{rate}%")

        ttft_str = _secs(ttft)
        tts_str = _secs(tts)

        tps_str = ""
        if tts is not None and tokens and total:
            # Та же формула, что и в metrics.add_metric: эффективный TPS.
            tps = tokens / total
            tps_str = (g if tps >= 15 else (y if tps >= 5 else r))(f"{tps:.1f}")

        avg_str = ""
        if avg_t is not None:
            avg_str = _secs(avg_t)

        n_str = dim(f"/{len(metrics.get(mid, []))}") if metrics and mid in metrics else ""

        if status == "OK":
            badge = g("OK   ")
            msg_out = ""
        elif status == "ERR":
            badge = r("ERR  ")
            msg_out = r(msg)
        else:
            badge = y("НЕТ  ")
            msg_out = y(msg)

        print(f"  {mid:<34} {ttft_str:<7} {tts_str:<7} {tps_str:<7} {avg_str:<8} "
              f"{s_badge:<9} {rate_str}{n_str:<7} {badge}{msg_out}")

    ok = sum(1 for _, s, _, _, _, _, _, _ in results if s == "OK")
    all_count = len(results)
    stable_n = sum(1 for r_ in results if model_status(metrics or {}, r_[0]) == "stable")
    print(f"\n  {dim('живых:')} {g(str(ok))} / {all_count}   "
          f"{dim('stable:')} {g(str(stable_n))}   "
          f"{dim('unstable:')} {y(str(sum(1 for r_ in results if model_status(metrics or {}, r_[0]) == 'unstable')))}   "
          f"{dim('dead:')} {r(str(sum(1 for r_ in results if model_status(metrics or {}, r_[0]) == 'dead')))}")
    print()


def print_top(metrics=None, n=10, sort_by="ttft"):
    """Топ N моделей по TTFT, TPS, success rate или combined-оценке."""
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()

    scored = []
    for mid in metrics:
        st = model_status(metrics, mid)
        avg_t = avg_ttft(metrics, mid)
        avg_p = avg_tps(metrics, mid)
        rate = success_rate(metrics, mid)

        if sort_by == "ttft" and avg_t is None:
            continue
        if sort_by == "tps" and avg_p is None:
            continue
        if sort_by == "rate" and rate is None:
            continue

        if sort_by == "ttft":
            score = avg_t or 999
        elif sort_by == "tps":
            score = -avg_p
        elif sort_by == "rate":
            score = -(rate or 0)
        else:
            # combined: быстрый TTFT, высокий success и запас TPS.
            score = ((avg_t or 999) * (1 + (100 - (rate or 0)) / 100)
                     - (avg_p or 0) * 0.1)

        scored.append((score, avg_t, avg_p, rate, st, mid))

    scored.sort()
    top = scored[:n]
    titles = {
        "ttft": "ТОП ПО TTFT",
        "tps": "ТОП ПО TPS",
        "rate": "ТОП ПО SUCCESS",
        "combined": "ТОП ПО COMBINED",
    }

    print(bold(f"  {titles.get(sort_by, 'ТОП')} ({len(top)})"))
    print(f"  {'#':<3} {'Модель':<34} {'TTFT':<8} {'TPS':<7} {'Статус':<9} {'Success':<8}")
    print(dim("  " + "─" * 76))
    for i, (_, avg_t, avg_p, rate, st, mid) in enumerate(top, 1):
        ttft_s = f"{avg_t:.3f}s" if avg_t is not None else "-"
        tps_s = f"{avg_p:.1f}" if avg_p is not None else "-"
        st_badge = g("stable") if st == "stable" else (y("unstable") if st == "unstable" else r("dead"))
        rate_s = f"{rate}%" if rate is not None else "-"
        print(f"  {i:<3} {mid:<34} {ttft_s:<8} {tps_s:<7} {st_badge:<9} {rate_s:<8}")


def print_stats(metrics=None):
    """Общая статистика по всем моделям."""
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()

    models = list(metrics.keys())
    if not models:
        print(dim("  нет данных метрик"))
        return

    total = len(models)
    stable_n = sum(1 for m in models if model_status(metrics, m) == "stable")
    unstable_n = sum(1 for m in models if model_status(metrics, m) == "unstable")
    dead_n = sum(1 for m in models if model_status(metrics, m) == "dead")
    unknown_n = sum(1 for m in models if model_status(metrics, m) == "unknown")

    all_ttfts = [avg_ttft(metrics, m) for m in models if avg_ttft(metrics, m) is not None]
    avg_ttft_all = round(sum(all_ttfts) / len(all_ttfts), 3) if all_ttfts else None
    min_ttft_all = round(min(all_ttfts), 3) if all_ttfts else None

    all_tts = [avg_tts(metrics, m) for m in models if avg_tts(metrics, m) is not None]
    avg_tts_all = round(sum(all_tts) / len(all_tts), 3) if all_tts else None

    all_tps = [avg_tps(metrics, m) for m in models if avg_tps(metrics, m) is not None]
    avg_tps_all = round(sum(all_tps) / len(all_tps), 1) if all_tps else None

    hs = health_score(metrics)

    print(bold("  СТАТИСТИКА"))
    print(f"  {dim('моделей всего:')}    {total}")
    print(f"  {g('stable:')}         {stable_n}   {y('unstable:')} {unstable_n}   {r('dead:')} {dead_n}   {dim('unknown:')} {unknown_n}")
    print(f"  {dim('средний TTFT:')}    {avg_ttft_all}s" if avg_ttft_all is not None else "")
    print(f"  {dim('минимальный TTFT:')} {min_ttft_all}s" if min_ttft_all is not None else "")
    print(f"  {dim('средний TTS:')}     {avg_tts_all}s" if avg_tts_all is not None else "")
    print(f"  {dim('средний TPS:')}     {avg_tps_all} tok/s" if avg_tps_all is not None else "")
    print(f"  {dim('health score:')}    {g(str(hs)) if hs >= 70 else (y(str(hs)) if hs >= 40 else r(str(hs)))}/100")
    print()


def print_info(model_id, metrics=None):
    """Детальная информация о модели."""
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()

    st = full_stats(metrics, model_id)
    if not st:
        print(dim(f"  нет данных для {model_id}"))
        return

    print(bold(f"  МОДЕЛЬ: {model_id}"))
    print(f"  {dim('статус:')}         {g('stable') if st['status'] == 'stable' else (y('unstable') if st['status'] == 'unstable' else r('dead'))}")
    print(f"  {dim('проверок:')}       {st['total']} ({g(str(st['ok']))} OK / {r(str(st['err']))} ERR / {y(str(st['no']))} NO)")
    print(f"  {dim('success rate:')}   {g(str(st['success_rate']) + '%') if st['success_rate'] >= 80 else y(str(st['success_rate']) + '%')}")
    print(f"  {dim('средний TTFT:')}   {st['avg_ttft']}s" if st['avg_ttft'] is not None else "")
    print(f"  {dim('мин TTFT:')}       {st['min_ttft']}s" if st['min_ttft'] is not None else "")
    print(f"  {dim('макс TTFT:')}      {st['max_ttft']}s" if st['max_ttft'] is not None else "")
    print(f"  {dim('средний TTS:')}    {st['avg_tts']}s" if st.get('avg_tts') is not None else "")
    print(f"  {dim('средний TPS:')}    {st['avg_tps']} tok/s" if st.get('avg_tps') is not None else "")
    if st.get("min_tps") is not None:
        print(f"  {dim('TPS min/max:')}   {st['min_tps']} / {st['max_tps']} tok/s")
    print(f"  {dim('первый тест:')}    {st['first_seen']}")
    print(f"  {dim('последний:')}      {st['last_seen']}")
    if st["fingerprints"]:
        print(f"  {dim('fingerprints:')}   {', '.join(st['fingerprints'])}")
    if st.get("fp_changed"):
        ch = st["fp_changed"]
        print(f"  {r('fingerprint сменился:')} {ch.get('from')} → {ch.get('to')}")
    if st.get("last_error"):
        print(f"  {dim('последняя ошибка:')} {r(st['last_error'])}")
    print()


def print_history_ascii(model_id, metrics=None, width=30):
    """ASCII-график TTFT по последним замерам."""
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()

    hist = metrics.get(model_id, [])
    if not hist:
        print(dim(f"  нет истории для {model_id}"))
        return

    ok_entries = [(h["ts"], h["ttft"]) for h in hist if h["status"] == "OK" and h["ttft"] is not None]
    if not ok_entries:
        print(dim(f"  нет успешных замеров для {model_id}"))
        return

    max_ttft = max(t for _, t in ok_entries)
    min_ttft = min(t for _, t in ok_entries)
    span = max_ttft - min_ttft or 1

    print(bold(f"  ИСТОРИЯ TTFT: {model_id}"))
    for ts, ttft in ok_entries[-20:]:
        bar_len = int((ttft - min_ttft) / span * width)
        bar = "█" * bar_len + "░" * (width - bar_len)
        time_str = _clock(ts)  # только HH:MM
        col = g if ttft < 2 else (y if ttft < 5 else r)
        print(f"  {time_str} {col(bar)} {ttft:.3f}s")
    print()


_SPARK = "▁▂▃▄▅▆▇█"


def _sparkline(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return _SPARK[3] * len(vals)
    return "".join(
        _SPARK[min(len(_SPARK) - 1, int((v - lo) / (hi - lo) * (len(_SPARK) - 1)))]
        for v in vals
    )


def print_trend(model_id, entries=None, limit=40):
    """Компактный тренд TTFT/TTS/TPS по полной истории."""
    if entries is None:
        from rb_tui.metrics import load_history
        entries = load_history(model_id, limit=limit)
    entries = [e for e in entries if e.get("model", model_id) == model_id][-limit:]
    if not entries:
        print(dim(f"  нет истории для {model_id}"))
        return

    ok = [e for e in entries if e.get("status") == "OK"]
    if not ok:
        print(dim(f"  нет успешных замеров для {model_id}"))
        return

    print(bold(f"  ТРЕНД: {model_id}"))
    print(dim(f"  {ok[0].get('ts', '?')} → {ok[-1].get('ts', '?')}  ({len(ok)} успешных)"))
    series = [
        ("TTFT", [e.get("ttft") for e in ok], "s"),
        ("TTS", [e.get("tts") for e in ok], "s"),
        ("TPS", [e.get("tps") for e in ok], " tok/s"),
    ]
    for label, values, unit in series:
        present = [v for v in values if v is not None]
        if not present:
            continue
        last = present[-1]
        print(f"  {dim(label + ':'):<8} {_sparkline(values):<42} "
              f"{last}{unit}  {dim('min')} {min(present)}{unit}  {dim('max')} {max(present)}{unit}")

    fp_changes = sum(1 for e in entries if e.get("fp_changed"))
    if fp_changes:
        print(f"  {r(f'⚠ fingerprint менялся {fp_changes} раз')}")
    errors = [e for e in entries if e.get("status") != "OK" and e.get("msg")]
    if errors:
        print(f"  {dim('последняя ошибка:')} {r(errors[-1]['msg'])}")
    print()


def print_lifetime(metrics=None):
    """Когда каждая модель появилась и сколько живёт."""
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()

    lf = lifetime(metrics)
    if not lf:
        print(dim("  нет данных"))
        return

    print(bold(f"  ВРЕМЯ ЖИЗНИ МОДЕЛЕЙ"))
    print(f"  {'Модель':<34} {'Появилась':<18} {'Проверок':<9} {'Успешно':<8}")
    print(dim("  " + "─" * 74))
    for mid, info in sorted(lf.items(), key=lambda x: x[1]["first_seen"]):
        print(f"  {mid:<34} {info['first_seen']:<18} {info['checks']:<9} {g(str(info['successful'])) if info['successful'] == info['checks'] else y(str(info['successful'])) + '/' + str(info['checks']):<8}")
    print()


def print_anomalies(metrics=None):
    """Найти и показать аномалии."""
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()

    anomalies = find_anomalies(metrics)
    if not anomalies:
        print(g("  аномалий не найдено"))
        return

    print(r(bold(f"  АНОМАЛИИ ({len(anomalies)})")))
    for a in anomalies:
        if a["type"] == "ttft_spike":
            print(f"  {r('⚠')} {a['model']}: TTFT вырос {a['ratio']}x ({a['avg_older']}s → {a['avg_recent']}s)")
        elif a["type"] == "tts_spike":
            print(f"  {r('⚠')} {a['model']}: TTS вырос {a['ratio']}x ({a['avg_older']}s → {a['avg_recent']}s)")
        elif a["type"] == "tps_drop":
            print(f"  {r('⚠')} {a['model']}: TPS упал {a['ratio']}x ({a['avg_older']} → {a['avg_recent']} tok/s)")
        elif a["type"] == "success_drop":
            print(f"  {r('⚠')} {a['model']}: success rate упал ({a['older_rate']*100}% → {a['recent_rate']*100}%)")
        elif a["type"] == "fingerprint_change":
            print(f"  {r('⚠')} {a['model']}: сменился fingerprint ({a['from']} → {a['to']})")
    print()


def print_grouped_by_owner(metrics=None, owned=None):
    """Группировка моделей по owned_by (из кэша каталога)."""
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()
    if owned is None:
        from rb_tui.sync import load_catalog_owned
        owned = load_catalog_owned()

    groups = {}
    for mid in metrics:
        owner = owned.get(mid)
        if not owner:
            # запасной вариант для старых кэшей
            owner = mid.split("/")[0] if "/" in mid else (mid.split("-")[0] if "-" in mid else "other")
        owner = str(owner).lower()
        groups.setdefault(owner, []).append(mid)

    print(bold("  ГРУППИРОВКА ПО ПРОВАЙДЕРУ"))
    for owner in sorted(groups.keys()):
        models = groups[owner]
        stable_n = sum(1 for m in models if model_status(metrics, m) == "stable")
        dead_n = sum(1 for m in models if model_status(metrics, m) == "dead")
        status_str = f"{g(str(stable_n))} stable" if stable_n else ""
        if dead_n:
            status_str += f" {r(str(dead_n))} dead" if status_str else f"{r(str(dead_n))} dead"
        print(f"  {bl(owner):<30} {len(models):>2} моделей  {status_str}")
    print()


def print_bench_results(results, model_id):
    """Вывод результатов бенчмарка."""
    print(bold(f"  БЕНЧМАРК: {model_id}"))
    for row in results:
        print(f"  {dim('промпт')} #{row['prompt']}")
        if row.get("status") == "OK":
            tps = row.get("tps")
            tps_s = f"{tps} tok/s" if tps is not None else "-"
            print(f"    {dim('TTFT:')} {row['ttft']}s  {dim('TTS:')} "
                  f"{row.get('tts') or '-'}s  {dim('TPS:')} {tps_s}")
            print(f"    {dim('токенов:')} {row['tokens']}  {dim('длина:')} {row['len']} симв.")
            text = row.get("content") or ""
            print(f"    {dim(text[:120] + '...' if len(text) > 120 else text)}")
        else:
            print(f"    {r('ошибка: ' + (row.get('msg') or row.get('status', '?')))}")
    print()


def print_compare_results(results, model_a, model_b):
    """A/B сравнение двух моделей."""
    print(bold(f"  СРАВНЕНИЕ: {model_a} vs {model_b}"))
    print(f"  {'Промпт':<8} {'TTFT A':<9} {'TTFT B':<9} {'TPS A':<8} {'TPS B':<8} "
          f"{'Токены A':<9} {'Токены B':<9}")
    print(dim("  " + "─" * 72))
    for row in results:
        def fmt(key, suffix=""):
            v = row.get(key)
            return f"{v}{suffix}" if v is not None else "-"
        print(f"  #{row['prompt']:<7} {fmt('ttft_A'):<9} {fmt('ttft_B'):<9} "
              f"{fmt('tps_A'):<8} {fmt('tps_B'):<8} "
              f"{row.get('tokens_A', 0):<9} {row.get('tokens_B', 0):<9}")
    print()


def print_speed_result(model_id, tps, err=""):
    if tps is not None:
        print(f"  {model_id:<34} {g(f'{tps} tok/s')}")
    else:
        print(f"  {model_id:<34} {r(f'ошибка: {err}')}")


def print_filtered(models, tag=None, metrics=None):
    """Отфильтрованный список моделей."""
    from rb_tui.utils import load_tags
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()

    tags = load_tags()

    for mid in sorted(models):
        model_tag = tags.get(mid, "")
        if tag and model_tag != tag:
            continue
        st = model_status(metrics, mid)
        st_badge = g("stable") if st == "stable" else (y("unstable") if st == "unstable" else (r("dead") if st == "dead" else dim("?")))
        avg_t = avg_ttft(metrics, mid)
        ttft_s = f"{avg_t:.3f}s" if avg_t is not None else "-"
        tag_s = f"[{bl(model_tag)}]" if model_tag else ""
        print(f"  {mid:<34} {st_badge:<9} {ttft_s:<8} {tag_s}")
