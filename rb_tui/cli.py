"""CLI-диспетчер: главная точка входа для rb-tui."""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime

from rb_tui import __version__
from rb_tui.utils import (
    CONFIG, CACHE, INTERACTIVE, g, r, y, bl, cy, dim, bold,
    fzf_multi, prune_backups, backup_config, load_tags, set_tag,
)
from rb_tui.config import (
    load_config, read_raw, apply_edits, append_log, diff_with_last_backup, config_check,
)
from rb_tui.api import api_key, fetch_catalog
from rb_tui import guard
from rb_tui.probe import probe_with_metrics, probe_all, speed_test, compare_models, ProbeThrottled
from rb_tui.metrics import (
    load_metrics, save_metrics, add_metric, model_status,
    avg_ttft, success_rate, full_stats, lifetime, health_score,
)
from rb_tui.render import (
    render_report, print_test_table, print_top, print_stats, print_info,
    print_history_ascii, print_lifetime, print_anomalies,
    print_grouped_by_owner, print_filtered, print_bench_results,
    print_compare_results, print_speed_result,
)
from rb_tui.sync import auto_sync, save_catalog, load_prev_catalog, auto_cleanup, auto_rollback
from rb_tui.alerts import (
    desktop_notify, notify_new_models, notify_stable_to_dead, notify_anomalies,
    send_webhook, build_webhook_payload,
)
from rb_tui.export import export_json, export_csv, export_html
from rb_tui.dashboard import serve


def probes_allowed():
    """Общая проверка: не в cooldown ли пробы."""
    line = guard.cooldown_status_line()
    if line:
        print(y("  ⏸ " + line))
        return False
    return True


def run_probe_cycle(base, key, live, budget=None, progress=False):
    """Безопасный цикл проб: cooldown → ротация → порция → стоп на детекте.

    Возвращает (results, throttled). results is None, если пробы на паузе.
    Метрики пишутся только для реально проверенных моделей: срабатывание
    защиты API никогда не превращается в статус dead.
    """
    line = guard.cooldown_status_line()
    if line:
        print(y("  ⏸ " + line))
        return None, False

    budget = guard.DEFAULT_BUDGET if budget is None else budget
    if guard.daily_remaining() <= 0:
        print(y(f"  суточный лимит проб исчерпан ({guard.DEFAULT_DAILY_BUDGET}), "
                f"продолжу завтра"))
        return [], False
    budget = guard.clamp_budget(budget)
    targets = guard.pick_targets(live, budget=budget)
    if not targets:
        print(dim("  в каталоге нет моделей для проверки"))
        return [], False

    print(dim(f"  проверяю {len(targets)} из {len(live)} моделей каталога "
              f"(пауза {guard.DEFAULT_DELAY:g}с, ротация)"))

    throttled = False
    try:
        results = probe_all(base, key, targets, progress=progress)
    except ProbeThrottled as e:
        results = e.results
        throttled = True
        left = guard.set_cooldown(reason=str(e.msg)[:80])
        print(r(f"  ⛔ API включил защиту: {e.msg}"))
        print(y(f"  прогон остановлен, пробы на паузе {guard.human_left(left)}."))
        print(dim(f"  проверено до срабатывания: {len(results)} — пишу только их."))

    if results:
        metrics = load_metrics()
        for mid, status, ttft, tts, total, tokens, fp, msg in results:
            metrics = add_metric(metrics, mid, status, ttft, total, tokens, fp, msg, tts=tts)
        save_metrics(metrics)
        guard.mark_probed([r[0] for r in results])

    return results, throttled


def main():
    # ── парсинг аргументов ──
    import argparse
    parser = argparse.ArgumentParser(
        prog="rb-tui",
        description="ReformBoss model catalog manager — sync, test, benchmark, dashboard",
    )
    parser.add_argument("--version", action="store_true", help="Показать версию")
    parser.add_argument("--sync", action="store_true",
                        help="Автосинхронизация каталога + проверка порции моделей")
    parser.add_argument("--report", action="store_true", help="Показать отчёт о каталоге")
    parser.add_argument("--test", action="store_true",
                        help="Проверить порцию моделей (бюджет + ротация)")
    parser.add_argument("--probe-model", type=str, default=None, metavar="MODEL",
                        help="Проверить одну модель (с учётом cooldown)")
    parser.add_argument("--probe-budget", nargs="?", const=guard.DEFAULT_BUDGET,
                        type=int, default=None, metavar="N",
                        help=f"Сколько моделей проверять за прогон (по умолч. {guard.DEFAULT_BUDGET})")
    parser.add_argument("--probe-reset", action="store_true",
                        help="Снять паузу проб (cooldown)")

    parser.add_argument("--top", nargs="?", const=10, type=int, default=None,
                        help="Топ N моделей по TTFT (по умолч. 10)")
    parser.add_argument("--stats", action="store_true", help="Общая статистика")
    parser.add_argument("--json", nargs="?", const="", type=str, default=None,
                        help="Экспорт метрик в JSON (без пути — в stdout)")
    parser.add_argument("--export-html", nargs="?", const="", type=str, default=None,
                        help="Экспорт HTML-отчёта (без пути — в stdout)")
    parser.add_argument("--export-csv", nargs="?", const="", type=str, default=None,
                        help="Экспорт CSV (без пути — в stdout)")
    parser.add_argument("--history", type=str, default=None, metavar="MODEL",
                        help="История TTFT модели (ASCII-график)")
    parser.add_argument("--diff", action="store_true", help="Diff с последним бэкапом")
    parser.add_argument("--bench", type=str, default=None, metavar="MODEL",
                        help="Бенчмарк модели на задачах")
    parser.add_argument("--compare", nargs=2, type=str, default=None, metavar=("A", "B"),
                        help="A/B сравнение двух моделей")
    parser.add_argument("--speed", type=str, default=None, metavar="MODEL",
                        help="Тест скорости генерации (tokens/s)")
    parser.add_argument("--serve", action="store_true", help="Запустить HTTP-дашборд")
    parser.add_argument("--serve-host", type=str, default="127.0.0.1",
                        help="Хост дашборда (по умолч. 127.0.0.1)")
    parser.add_argument("--serve-port", type=int, default=9090,
                        help="Порт дашборда (по умолч. 9090)")
    parser.add_argument("--config-check", action="store_true", help="Проверить конфиг")
    parser.add_argument("--prune-backups", nargs="?", const=30, type=int, default=None,
                        help="Удалить бэкапы старше N дней (по умолч. 30)")
    parser.add_argument("--fuzzy", type=str, default=None, metavar="QUERY",
                        help="Поиск/рекомендация модели")
    parser.add_argument("--filter", type=str, default=None, metavar="TAG",
                        help="Фильтр по тегу")
    parser.add_argument("--info", type=str, default=None, metavar="MODEL",
                        help="Информация о модели")
    parser.add_argument("--lifetime", action="store_true", help="Время жизни моделей")
    parser.add_argument("--tag", nargs=2, type=str, default=None, metavar=("MODEL", "TAG"),
                        help="Установить тег модели")
    parser.add_argument("--watch", action="store_true", help="Режим наблюдения (каждые N сек)")
    parser.add_argument("--anomalies", action="store_true", help="Найти аномалии")
    parser.add_argument("--group-by-owner", action="store_true", help="Группировка по провайдеру")
    parser.add_argument("--webhook", type=str, default=None, metavar="URL",
                        help="URL вебхука для отправки сводки")

    args = parser.parse_args()

    if args.version:
        print(f"rb-tui v{__version__}")
        return

    # ── быстрые команды без конфига ──
    if args.probe_reset:
        guard.clear_cooldown()
        print(g("  пауза проб снята"))
        return

    if args.prune_backups is not None:
        removed = prune_backups(days=args.prune_backups)
        print(f"  удалено {removed} бэкапов старше {args.prune_backups} дней")
        return

    if not os.path.isfile(CONFIG):
        print(r(f"конфиг не найден: {CONFIG}"))
        sys.exit(1)

    # ── загрузка конфига ──
    try:
        raw, settings, cfg_models = load_config()
    except Exception as e:
        ok, msg = auto_rollback()
        if ok:
            print(y(f"конфиг был сломан, откатился к {msg}"))
            try:
                raw, settings, cfg_models = load_config()
            except Exception as e2:
                print(r(f"после отката всё ещё не читается: {e2}"))
                sys.exit(1)
        else:
            print(r(f"не смог разобрать конфиг: {e} ({msg})"))
            sys.exit(1)

    key = api_key(settings)
    base = settings.get("baseURL", "https://api.reformboss.com/v1")
    if not key:
        print(r("apiKey не найден."))
        sys.exit(1)

    # ── команды, которым не нужен каталог ──
    if args.diff:
        print(diff_with_last_backup())
        return

    if args.config_check:
        for issue in config_check():
            print(f"  {issue}")
        return

    if args.info:
        metrics = load_metrics()
        print_info(args.info, metrics)
        return

    if args.history:
        metrics = load_metrics()
        print_history_ascii(args.history, metrics)
        return

    if args.lifetime:
        metrics = load_metrics()
        print_lifetime(metrics)
        return

    if args.anomalies:
        metrics = load_metrics()
        print_anomalies(metrics)
        return

    if args.stats:
        metrics = load_metrics()
        print_stats(metrics)
        return

    if args.top is not None:
        metrics = load_metrics()
        print_top(metrics, n=args.top)
        return

    if args.json is not None:
        out = export_json(args.json or None)
        if args.json:
            print(f"  экспорт: {out}")
        else:
            print(out)
        return

    if args.export_html is not None:
        out = export_html(args.export_html or None)
        if args.export_html:
            print(f"  экспорт: {out}")
        else:
            print(out)
        return

    if args.export_csv is not None:
        out = export_csv(args.export_csv or None)
        if args.export_csv:
            print(f"  экспорт: {out}")
        else:
            print(out)
        return

    if args.group_by_owner:
        metrics = load_metrics()
        print_grouped_by_owner(metrics)
        return

    if args.tag:
        set_tag(args.tag[0], args.tag[1])
        print(f"  тег '{args.tag[1]}' установлен для {args.tag[0]}")
        return

    if args.serve:
        serve(host=args.serve_host, port=args.serve_port)
        return

    if args.fuzzy:
        _cmd_fuzzy(args.fuzzy, metrics=load_metrics())
        return

    if args.filter:
        metrics = load_metrics()
        # filtering requires live models, get them
        live, _, err = fetch_catalog(base, key)
        if live is None:
            print(r(f"каталог недоступен: {err}"))
            return
        print_filtered(live, tag=args.filter, metrics=metrics)
        return

    if args.bench:
        if not probes_allowed():
            return
        _cmd_bench(base, key, args.bench)
        return

    if args.compare:
        if not probes_allowed():
            return
        _cmd_compare(base, key, args.compare[0], args.compare[1])
        return

    if args.speed:
        if not probes_allowed():
            return
        _cmd_speed(base, key, args.speed)
        return

    if args.webhook:
        metrics = load_metrics()
        payload = build_webhook_payload(metrics)
        ok = send_webhook(args.webhook, payload)
        print(g("вебхук отправлен") if ok else r("ошибка вебхука"))
        return

    if args.watch:
        _cmd_watch(base, key)
        return

    # ── fetch catalog ──
    live, owned, err = fetch_catalog(base, key)
    if live is None:
        print(r(f"каталог недоступен: {err}"))
        sys.exit(1)

    new = [m for m in live if m not in cfg_models]
    gone = [m for m in cfg_models if m not in live]

    prev_date, prev = load_prev_catalog()
    if prev is None:
        appeared, disappeared = [], []
    else:
        appeared = [m for m in live if m not in prev]
        disappeared = [m for m in prev if m not in live]
    save_catalog(live)

    # ── --probe-model ──
    if args.probe_model:
        mid = args.probe_model
        line = guard.cooldown_status_line()
        if line:
            print(y("  ⏸ " + line))
            return
        if guard.daily_remaining() <= 0:
            print(y(f"  суточный лимит проб исчерпан ({guard.DEFAULT_DAILY_BUDGET}), "
                    f"продолжу завтра"))
            return
        if mid not in live:
            print(r(f"  {mid} нет в каталоге API — проверять бессмысленно"))
            return
        status, ttft, tts, total, tokens, fp, msg = probe_with_metrics(base, key, mid)
        if status == "THROTTLE":
            left = guard.set_cooldown(reason=str(msg)[:80])
            print(r(f"  ⛔ API включил защиту: {msg}"))
            print(y(f"  пробы на паузе {guard.human_left(left)}, метрика не записана"))
            return
        metrics = load_metrics()
        metrics = add_metric(metrics, mid, status, ttft, total, tokens, fp, msg, tts=tts)
        save_metrics(metrics)
        guard.mark_probed([mid])
        tts_s = f"  tts={tts}" if tts is not None else ""
        print(f"  {mid}: {status}  ttft={ttft}{tts_s}  total={total}  tokens={tokens}")
        return

    # ── --sync ──
    if args.sync:
        auto_sync(new, gone, live)
        # безопасный тест: только живые модели, порция с ротацией
        results, _throttled = run_probe_cycle(
            base, key, live, budget=args.probe_budget, progress=True)
        if results is None:
            return

        metrics = load_metrics()
        ok_count = sum(1 for _, s, _, _, _, _, _, _ in results if s == "OK")
        if results:
            print(f"  {g(f'✅ {ok_count}/{len(results)} доступны')}, метрики сохранены")
        else:
            print(y("  метрики не обновлялись"))

        # Уведомления
        target_live = [m for m in live if m not in new]
        notify_new_models(new)
        notify_stable_to_dead(metrics)
        notify_anomalies(metrics)

        # Автоочистка
        auto_cleanup(days=30)

        # Сводка в лог
        with open(os.path.join(CACHE, "auto-sync.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                    f"sync: тест {ok_count}/{len(results)} живых\n")
        return

    # ── --report / --test ──
    def show():
        render_report(cfg_models, live, new, gone, key_ok=True, base=base,
                      prev_date=prev_date, appeared=appeared, disappeared=disappeared)

    if args.report or args.test or not INTERACTIVE:
        show()
        if args.test:
            results, _throttled = run_probe_cycle(
                base, key, live, budget=args.probe_budget)
            if results:
                print_test_table(results, load_metrics())
            elif results is not None:
                print(y("  нет результатов для таблицы"))
        return

    # ── интерактивный режим ──
    show()
    last_results = None

    while True:
        opts = []
        if new:
            opts.append(("1", f"добавить новые в конфиг ({len(new)})"))
        if gone:
            opts.append(("2", f"убрать пропавшие ({len(gone)})"))
        opts.append(("3", "тест доступности"))
        if last_results or new or gone:
            opts.append(("4", "записать сводку проверки в лог конфига"))
        opts.append(("q", "выход"))
        print()
        for k, v in opts:
            print(dim("  [") + bold(k) + dim("] ") + v)
        try:
            choice = input(cy("  выбор: ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "q":
            break

        elif choice == "1" and new:
            picked = fzf_multi(new, "Tab - выбрать, Enter - подтвердить, Esc - отмена",
                               "добавить> ")
            if picked:
                ok, msg = apply_edits(adds=picked, comment_out=[], deletes=[],
                                      note_date=datetime.now().strftime("%d.%m.%Y"))
                if ok:
                    print(g(f"добавлено {len(picked)}, бэкап: {msg}"))
                    raw, settings, cfg_models = load_config()
                    new = [m for m in live if m not in cfg_models]
                    gone = [m for m in cfg_models if m not in live]
                    show()
                else:
                    print(r(msg))

        elif choice == "2" and gone:
            picked = fzf_multi(gone, "Tab - выбрать, Enter - подтвердить, Esc - отмена",
                               "убрать> ")
            if picked:
                print(f"  действие: {c('c', '1')} закомментировать · "
                      f"{c('d', '1')} удалить · Enter отмена")
                act = input(cy("  выбор: ")).strip().lower()
                if act in ("c", "d"):
                    date = datetime.now().strftime("%d.%m.%Y")
                    ok, msg = apply_edits(
                        adds=[], comment_out=picked if act == "c" else [],
                        deletes=picked if act == "d" else [], note_date=date)
                    if ok:
                        verb = "закомментировано" if act == "c" else "удалено"
                        print(g(f"{verb} {len(picked)}, бэкап: {msg}"))
                        raw, settings, cfg_models = load_config()
                        new = [m for m in live if m not in cfg_models]
                        gone = [m for m in cfg_models if m not in live]
                        show()
                    else:
                        print(r(msg))

        elif choice == "3":
            results, _throttled = run_probe_cycle(
                base, key, live, budget=args.probe_budget)
            if results:
                print_test_table(results, load_metrics())
                last_results = results
            elif results is not None:
                print(y("  нет результатов для таблицы"))

        elif choice == "4" and (last_results or new or gone):
            ts = datetime.now().strftime("%d.%m.%Y %H:%M")
            lines = [f"── Проверка {ts} ──"]
            if last_results:
                oks = [m for m, s, _, _, _, _, _, _ in last_results if s == "OK"]
                errs = [m for m, s, _, _, _, _, _, _ in last_results if s == "ERR"]
                nos = [m for m, s, _, _, _, _, _, _ in last_results if s == "NO"]
                if oks:
                    lines.append(f"OK ({len(oks)}): {', '.join(oks)}")
                if errs:
                    lines.append(f"ERR ({len(errs)}): {', '.join(errs)}")
                if nos:
                    lines.append(f"без ответа ({len(nos)}): {', '.join(nos)}")
            if new:
                lines.append(f"появились в каталоге: {', '.join(new)}")
            if gone:
                lines.append(f"пропали из каталога: {', '.join(gone)}")
            ok, msg = append_log(lines)
            print(g(f"сводка записана в конфиг, бэкап: {msg}") if ok else r(msg))

        else:
            print(y("  нет такого пункта"))

    print(dim("  готово."))


# ── helpers ──

def c(txt, code):
    from rb_tui.utils import COLOR
    return f"\033[{code}m{txt}\033[0m" if COLOR else str(txt)


def _cmd_fuzzy(query, metrics):
    """Поиск модели по описанию / рекомендация."""
    query = query.lower()
    results = []

    # Ищем по имени
    for mid in metrics:
        if query in mid.lower() or query in mid.replace("-", " ").lower():
            st = model_status(metrics, mid)
            avg_t = avg_ttft(metrics, mid)
            rate = success_rate(metrics, mid)
            results.append((mid, st, avg_t, rate))

    if not results:
        # Если ничего не нашли — показываем топ по задаче
        print(dim(f"  по запросу '{query}' ничего не найдено. Показываю топ:"))
        print_top(metrics, n=5)
        return

    print(bold(f"  РЕЗУЛЬТАТЫ ПО ЗАПРОСУ: {query}"))
    print(f"  {'Модель':<34} {'Статус':<9} {'TTFT':<8} {'Success':<8}")
    print(dim("  " + "─" * 65))
    for mid, st, avg_t, rate in sorted(results, key=lambda x: avg_ttft(metrics, x[0]) or 999):
        st_badge = g("stable") if st == "stable" else (y("unstable") if st == "unstable" else (r("dead") if st == "dead" else dim("?")))
        ttft_s = f"{avg_t:.3f}s" if avg_t else "-"
        rate_s = f"{rate}%" if rate is not None else "-"
        print(f"  {mid:<34} {st_badge:<9} {ttft_s:<8} {rate_s:<8}")

    # Рекомендация
    rec = [m for m, s, _, r in results if s == "stable" and r and r >= 80]
    if not rec:
        rec = [m for m, _, _, _ in results]
    if rec:
        best = min(rec, key=lambda m: (avg_ttft(metrics, m) or 999))
        print(f"\n  {g('→ рекомендуем:')} {bold(best)} (TTFT {avg_ttft(metrics, best)}s)")


def _cmd_bench(base, key, model_id):
    """Бенчмарк модели на нескольких задачах."""
    from rb_tui.probe import probe_with_metrics
    prompts = [
        "Write a Python function to merge two sorted lists.",
        "Explain the difference between TCP and UDP in simple terms.",
        "Write a short poem about artificial intelligence.",
    ]

    print(bold(f"  БЕНЧМАРК: {model_id}"))
    print(dim(f"  тестирую на {len(prompts)} промптах..."))

    for i, prompt in enumerate(prompts, 1):
        body = json.dumps({
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
        }).encode()
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        req = urllib.request.Request(
            base.rstrip("/") + "/chat/completions", data=body, headers=headers)
        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
            total = round(time.monotonic() - start, 3)
            j = json.loads(raw)
            content = j.get("choices", [{}])[0].get("message", {}).get("content", "")
            tokens = j.get("usage", {}).get("total_tokens", 0)
            tps = round(tokens / total, 2) if total > 0 else 0
            print(f"  #{i} {dim(str(total) + 's')} TTFT={total}s tok={tokens} speed={tps} tok/s")
            print(f"    {dim(content[:120] + '...' if len(content) > 120 else content)}")
        except Exception as e:
            print(f"  #{i} {r('ошибка: ' + str(e)[:60])}")
    print()


def _cmd_compare(base, key, model_a, model_b):
    """A/B сравнение двух моделей."""
    results = compare_models(base, key, model_a, model_b)
    print_compare_results(results, model_a, model_b)


def _cmd_speed(base, key, model_id):
    """Замерить tokens/s."""
    tps, err = speed_test(base, key, model_id)
    print_speed_result(model_id, tps, err)


def _cmd_watch(base, key, interval=300):
    """Режим наблюдения: каждые N секунд обновлять статус порцией моделей."""
    from rb_tui.metrics import load_metrics, model_status

    print(bold("  WATCH MODE"))
    print(dim(f"  обновление каждые {interval} сек, Ctrl+C для выхода"))
    print()

    try:
        while True:
            live, _, err = fetch_catalog(base, key)
            if live is None:
                print(r(f"  каталог недоступен: {err}"))
                time.sleep(interval)
                continue

            results, _throttled = run_probe_cycle(base, key, live, progress=False)

            ts = datetime.now().strftime("%H:%M:%S")
            if results is None:
                print(f"  [{ts}] пробы на паузе")
            else:
                metrics = load_metrics()
                ok = sum(1 for _, s, _, _, _, _, _, _ in results if s == "OK")
                stable = sum(1 for r_ in results if model_status(metrics, r_[0]) == "stable")
                print(f"  [{ts}] {g(str(ok))}/{len(results)} живых, {g(str(stable))} stable")

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  watch остановлен")


if __name__ == "__main__":
    main()
