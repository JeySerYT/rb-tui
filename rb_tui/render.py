"""Вывод в терминал: таблицы, топ, статистика, отчёты."""

from rb_tui.utils import (
    g, r, y, bl, cy, dim, bold,
)
from rb_tui.metrics import (
    model_status, avg_ttft, success_rate, full_stats,
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


def print_test_table(results, metrics=None):
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()
    print(bold(f"  ТЕСТ ДОСТУПНОСТИ ({len(results)} моделей)"))
    print(f"  {'Модель':<34} {'TTFT':<6} {'Ср.TTFT':<8} {'Статус':<9} {'%/N':<7} {'Ошибка'}")
    print(dim("  " + "─" * 90))
    for mid, status, ttft, total, tokens, fp, msg in results:
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

        ttft_str = ""
        if ttft is not None:
            col = g if ttft < 2 else (y if ttft < 5 else r)
            ttft_str = col(f"{ttft:.3f}")

        avg_str = ""
        if avg_t is not None:
            col = g if avg_t < 2 else (y if avg_t < 5 else r)
            avg_str = col(f"{avg_t:.3f}")

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

        print(f"  {mid:<34} {ttft_str:<6} {avg_str:<8} {s_badge:<9} {rate_str}{n_str:<7} {badge}{msg_out}")

    ok = sum(1 for _, s, _, _, _, _, _ in results if s == "OK")
    all_count = len(results)
    stable_n = sum(1 for r_ in results if model_status(metrics or {}, r_[0]) == "stable")
    print(f"\n  {dim('живых:')} {g(str(ok))} / {all_count}   "
          f"{dim('stable:')} {g(str(stable_n))}   "
          f"{dim('unstable:')} {y(str(sum(1 for r_ in results if model_status(metrics or {}, r_[0]) == 'unstable')))}   "
          f"{dim('dead:')} {r(str(sum(1 for r_ in results if model_status(metrics or {}, r_[0]) == 'dead')))}")
    print()


def print_top(metrics=None, n=10, sort_by="ttft"):
    """Топ N моделей по TTFT или стабильности."""
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()

    # Собираем все модели из метрик
    scored = []
    for mid in metrics:
        st = model_status(metrics, mid)
        avg_t = avg_ttft(metrics, mid)
        rate = success_rate(metrics, mid)

        if sort_by == "ttft" and avg_t is None:
            continue
        if sort_by == "rate" and rate is None:
            continue

        score = 0
        if sort_by == "ttft":
            score = avg_t or 999
        elif sort_by == "rate":
            score = -(rate or 0)
        else:
            # combined: низкий TTFT + высокий success rate
            score = (avg_t or 999) * (1 - (rate or 0) / 100 + 1)

        scored.append((score, avg_t, rate, st, mid))

    scored.sort()
    top = scored[:n]

    print(bold(f"  ТОП-{len(top)} МОДЕЛЕЙ"))
    print(f"  {'#':<3} {'Модель':<34} {'TTFT':<8} {'Статус':<9} {'Success':<8}")
    print(dim("  " + "─" * 68))
    for i, (_, avg_t, rate, st, mid) in enumerate(top, 1):
        ttft_s = f"{avg_t:.3f}s" if avg_t else "-"
        st_badge = g("stable") if st == "stable" else (y("unstable") if st == "unstable" else r("dead"))
        rate_s = f"{rate}%" if rate is not None else "-"
        print(f"  {i:<3} {mid:<34} {ttft_s:<8} {st_badge:<9} {rate_s:<8}")


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

    hs = health_score(metrics)

    print(bold("  СТАТИСТИКА"))
    print(f"  {dim('моделей всего:')}    {total}")
    print(f"  {g('stable:')}         {stable_n}   {y('unstable:')} {unstable_n}   {r('dead:')} {dead_n}   {dim('unknown:')} {unknown_n}")
    print(f"  {dim('средний TTFT:')}    {avg_ttft_all}s" if avg_ttft_all else "")
    print(f"  {dim('минимальный TTFT:')} {min_ttft_all}s" if min_ttft_all else "")
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
    print(f"  {dim('средний TTFT:')}   {st['avg_ttft']}s" if st['avg_ttft'] else "")
    print(f"  {dim('мин TTFT:')}       {st['min_ttft']}s" if st['min_ttft'] else "")
    print(f"  {dim('макс TTFT:')}      {st['max_ttft']}s" if st['max_ttft'] else "")
    print(f"  {dim('первый тест:')}    {st['first_seen']}")
    print(f"  {dim('последний:')}      {st['last_seen']}")
    if st['fingerprints']:
        print(f"  {dim('fingerprints:')}   {', '.join(st['fingerprints'])}")
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
        time_str = ts[-5:]  # только HH:MM
        col = g if ttft < 2 else (y if ttft < 5 else r)
        print(f"  {time_str} {col(bar)} {ttft:.3f}s")
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
        elif a["type"] == "success_drop":
            print(f"  {r('⚠')} {a['model']}: success rate упал ({a['older_rate']*100}% → {a['recent_rate']*100}%)")
    print()


def print_grouped_by_owner(metrics=None):
    """Группировка моделей по owned_by."""
    if metrics is None:
        from rb_tui.metrics import load_metrics
        metrics = load_metrics()

    # Пытаемся вытащить owner из ID модели
    groups = {}
    for mid in metrics:
        if "/" in mid:
            owner = mid.split("/")[0]
        else:
            owner = mid.split("-")[0] if "-" in mid else "other"
        owner = owner.lower()
        if owner not in groups:
            groups[owner] = []
        groups[owner].append(mid)

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
        print(f"    {dim('TTFT:')} {row['ttft']}s" if row['ttft'] else f"    {r('ошибка')}")
        print(f"    {dim('токенов:')} {row['tokens']}")
        print(f"    {dim('длина ответа:')} {row['len']} симв.")
    print()


def print_compare_results(results, model_a, model_b):
    """A/B сравнение двух моделей."""
    print(bold(f"  СРАВНЕНИЕ: {model_a} vs {model_b}"))
    print(f"  {'Промпт':<8} {'TTFT A':<10} {'TTFT B':<10} {'Токены A':<10} {'Токены B':<10} {'Длина A':<10} {'Длина B':<10}")
    print(dim("  " + "─" * 70))
    for row in results:
        ttft_a = f"{row['ttft_A']:.3f}s" if row.get('ttft_A') else "-"
        ttft_b = f"{row['ttft_B']:.3f}s" if row.get('ttft_B') else "-"
        print(f"  #{row['prompt']:<7} {ttft_a:<10} {ttft_b:<10} {row.get('tokens_A', 0):<10} {row.get('tokens_B', 0):<10} {row.get('len_A', 0):<10} {row.get('len_B', 0):<10}")
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
        ttft_s = f"{avg_t:.3f}s" if avg_t else "-"
        tag_s = f"[{bl(model_tag)}]" if model_tag else ""
        print(f"  {mid:<34} {st_badge:<9} {ttft_s:<8} {tag_s}")
