"""CLI-диспетчер: главная точка входа для rb-tui."""

import os
import sys
import time
from datetime import datetime

from rb_tui import __version__
from rb_tui import console, crash, paths
from rb_tui.utils import (
    CONFIG, INTERACTIVE, g, r, y, bl, cy, dim, bold,
    fzf_multi, prune_backups, backup_config, load_tags, set_tag,
)
from rb_tui.config import (
    load_config, read_raw, apply_edits, append_log, diff_with_last_backup, config_check,
)
from rb_tui.api import api_key, fetch_catalog
from rb_tui import guard
from rb_tui.probe import (
    probe_with_metrics, probe_all, speed_test, compare_models, bench_model,
    ProbeThrottled,
)
from rb_tui.metrics import (
    load_metrics, save_metrics, record_metric,
    prune_history, model_status, avg_ttft, success_rate, full_stats, lifetime,
    health_score,
)
from rb_tui.render import (
    render_report, render_home, render_menu,
    print_test_table, print_top, print_stats, print_info,
    print_history_ascii, print_trend, print_lifetime, print_anomalies,
    print_grouped_by_owner, print_filtered, print_bench_results,
    print_compare_results, print_speed_result,
)
from rb_tui.sync import (
    auto_sync, save_catalog, load_prev_catalog, load_catalog_owned,
    auto_cleanup, auto_rollback, log_auto,
)
from rb_tui.alerts import (
    desktop_notify, notify_new_models, notify_stable_to_dead, notify_anomalies,
    send_webhook, build_webhook_payload, test_notify, webhook_format, notify_hint,
)
from rb_tui.export import export_json, export_csv, export_html
from rb_tui.dashboard import serve


def fail(message, code=1):
    """Показать ошибку и выйти, не закрывая окно на Windows мгновенно."""
    print(r(message))
    console.wait_before_exit()
    sys.exit(code)


def _ask(prompt):
    """Опрос в интерактивном меню; None при EOF/Ctrl+C."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def reserve_probes(count, models=None):
    """Проверить cooldown и суточный бюджет, затем списать запросы."""
    ok, msg = guard.reserve(count, models)
    if not ok:
        prefix = "  ⏸ " if "на паузе" in msg else "  "
        print(y(prefix + msg))
        return False
    return True


def run_probe_cycle(base, key, live, budget=None, progress=False, verbose=True):
    """Безопасный цикл проб: cooldown → ротация → порция → стоп на детекте.

    Возвращает (results, throttled). results is None, если пробы на паузе.
    Метрики пишутся только для реально проверенных моделей: срабатывание
    защиты API никогда не превращается в статус dead.
    """
    line = guard.cooldown_status_line()
    if line:
        if verbose:
            print(y("  ⏸ " + line))
        return None, False

    budget = guard.DEFAULT_BUDGET if budget is None else budget
    if guard.daily_remaining() <= 0:
        if verbose:
            print(y(f"  суточный лимит проб исчерпан ({guard.DEFAULT_DAILY_BUDGET}), "
                    f"продолжу завтра"))
        return [], False
    budget = guard.clamp_budget(budget)
    targets = guard.pick_targets(live, budget=budget)
    if not targets:
        if verbose:
            print(dim("  в каталоге нет моделей для проверки"))
        return [], False

    if verbose:
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
            metrics = record_metric(
                metrics, mid, status, ttft, total, tokens, fp, msg, tts=tts,
            )
        save_metrics(metrics)
        guard.mark_probed([r[0] for r in results])

    return results, throttled


def handle_throttle(e):
    """Остановиться, уйти в cooldown и объяснить это пользователю."""
    left = guard.set_cooldown(reason=str(e.msg)[:80])
    print(r(f"  ⛔ API включил защиту: {e.msg}"))
    print(y(f"  пробы на паузе {guard.human_left(left)}."))


def notify_update_available():
    """Показать доступное обновление при запуске standalone-бинарника."""
    if not getattr(sys, "frozen", False):
        return
    try:
        from rb_tui import update as updater

        latest = updater.check_cached()
    except Exception:
        return
    if latest:
        print(y(f"  ↑ доступна новая версия v{latest} (у тебя v{__version__})"))
        print(dim("    обновить: rb-tui --update"))


def main():
    # CONFIG переопределяется флагом --config; остальное — аргументы.
    global CONFIG
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
                        help="Топ N моделей (по умолч. 10)")
    parser.add_argument("--sort", choices=["ttft", "tps", "rate", "combined"],
                        default="ttft",
                        help="Сортировка для --top: ttft, tps, rate, combined")
    parser.add_argument("--trend", type=str, default=None, metavar="MODEL",
                        help="Тренд TTFT/TTS/TPS по полной истории")
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
    parser.add_argument("--prune-metrics", nargs="?", const=90, type=int, default=None,
                        help="Удалить историю метрик старше N дней (по умолч. 90)")
    parser.add_argument("--test-notify", action="store_true",
                        help="Проверить desktop-уведомления")
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
    parser.add_argument("--watch-interval", type=int, default=300, metavar="SEC",
                        help="Интервал --watch в секундах (по умолч. 300)")
    parser.add_argument("--watch-runs", type=int, default=0, metavar="N",
                        help="Сколько циклов --watch выполнить (0 — бесконечно)")
    parser.add_argument("--anomalies", action="store_true", help="Найти аномалии")
    parser.add_argument("--group-by-owner", action="store_true", help="Группировка по провайдеру")
    parser.add_argument("--webhook", type=str, default=None, metavar="URL",
                        help="URL вебхука для отправки сводки")
    parser.add_argument("--update", action="store_true",
                        help="Обновить standalone-бинарник до последнего релиза")
    parser.add_argument("--update-check", action="store_true",
                        help="Проверить, есть ли новая версия")
    parser.add_argument("--config", type=str, default=None, metavar="PATH",
                        help="Путь к opencode.json/jsonc (иначе ищется по ОС)")
    parser.add_argument("--diag", action="store_true",
                        help="Показать диагностику для отчёта об ошибке")
    parser.add_argument("--report-bug", nargs="?", const="", type=str, default=None,
                        metavar="FILE",
                        help="Открыть Issue с сохранённым отчётом о падении")

    args = parser.parse_args()

    # Перехват падений ставим до любой реальной работы.
    crash.install()

    if args.config:
        CONFIG = paths.set_config_path(args.config)

    if args.version:
        print(f"rb-tui v{__version__}")
        return

    if args.diag:
        print(crash.diagnostics_text())
        return

    if args.report_bug is not None:
        try:
            crash.send_report(args.report_bug or None)
        except (OSError, ValueError) as e:
            fail(f"  {e}")
        return

    if args.update_check:
        from rb_tui import update as updater
        try:
            current, latest, newer = updater.check()
        except updater.UpdateError as e:
            fail(f"  {e}")
        if newer:
            print(y(f"  есть новая версия: v{current} → v{latest}"))
            print(dim("  обновить: rb-tui --update"))
        else:
            print(g(f"  уже последняя версия: v{current}"))
        return

    if args.update:
        from rb_tui import update as updater
        try:
            updater.update(progress=lambda msg: print(msg))
        except updater.UpdateError as e:
            fail(f"  {e}")
        return

    notify_update_available()

    # ── быстрые команды без конфига ──
    if args.probe_reset:
        guard.clear_cooldown()
        print(g("  пауза проб снята"))
        return

    if args.prune_backups is not None:
        removed = prune_backups(days=args.prune_backups)
        print(f"  удалено {removed} бэкапов старше {args.prune_backups} дней")
        return

    if args.prune_metrics is not None:
        kept, removed = prune_history(days=args.prune_metrics)
        print(f"  история: оставлено {kept}, удалено {removed} записей "
              f"старше {args.prune_metrics} дней")
        return

    if args.test_notify:
        ok = test_notify()
        print(g("  уведомление отправлено") if ok
              else r(f"  не удалось: {notify_hint()}"))
        return

    if not os.path.isfile(CONFIG):
        print(r(f"конфиг не найден: {CONFIG}"))
        print(dim("  проверены пути:"))
        for path in paths.searched_paths():
            print(dim(f"    {path}"))
        print(dim("  укажи путь вручную: rb-tui --config <файл> "
                  "или переменной RB_TUI_CONFIG"))
        fail("  без конфига OpenCode работать не с чем")

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
                fail(f"после отката всё ещё не читается: {e2}")
        else:
            fail(f"не смог разобрать конфиг: {e} ({msg})")

    key = api_key(settings)
    base = settings.get("baseURL", "https://api.reformboss.com/v1")
    if not key:
        fail("apiKey не найден.")

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

    if args.trend:
        print_trend(args.trend)
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
        print_top(metrics, n=args.top, sort_by=args.sort)
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
        print_grouped_by_owner(metrics, owned=load_catalog_owned())
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
        if not reserve_probes(3, [args.bench]):
            return
        try:
            _cmd_bench(base, key, args.bench)
        except ProbeThrottled as e:
            handle_throttle(e)
        return

    if args.compare:
        if not reserve_probes(6, args.compare):
            return
        try:
            _cmd_compare(base, key, args.compare[0], args.compare[1])
        except ProbeThrottled as e:
            handle_throttle(e)
        return

    if args.speed:
        if not reserve_probes(1, [args.speed]):
            return
        try:
            _cmd_speed(base, key, args.speed)
        except ProbeThrottled as e:
            handle_throttle(e)
        return

    if args.webhook:
        metrics = load_metrics()
        fmt = webhook_format(args.webhook)
        payload = build_webhook_payload(metrics, fmt=fmt)
        ok = send_webhook(args.webhook, payload)
        print(g("вебхук отправлен") if ok else r("ошибка вебхука"))
        return

    if args.watch:
        _cmd_watch(
            base, key, interval=args.watch_interval,
            runs=args.watch_runs, budget=args.probe_budget,
        )
        return

    # ── fetch catalog ──
    live, owned, err = fetch_catalog(base, key)
    if live is None:
        fail(f"каталог недоступен: {err}")

    new = [m for m in live if m not in cfg_models]
    gone = [m for m in cfg_models if m not in live]

    prev_date, prev = load_prev_catalog()
    if prev is None:
        appeared, disappeared = [], []
    else:
        appeared = [m for m in live if m not in prev]
        disappeared = [m for m in prev if m not in live]
    save_catalog(live, owned)

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
        metrics = record_metric(
            metrics, mid, status, ttft, total, tokens, fp, msg, tts=tts,
        )
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
        log_auto(f"sync: тест {ok_count}/{len(results)} живых")
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
    last_results = None

    def redraw():
        render_home(cfg_models, live, new, gone, load_metrics(), prev_date,
                    appeared, disappeared, base, __version__)

    redraw()
    while True:
        items = []
        if new:
            items.append(("Каталог", "1", f"добавить новые в конфиг ({len(new)})"))
        if gone:
            items.append(("Каталог", "2", f"убрать пропавшие ({len(gone)})"))
        items += [
            ("Каталог", "3", "тест доступности (бюджет + ротация)"),
            ("Каталог", "4", "записать сводку в лог конфига"),
            ("Метрики", "5", "сводка и топ моделей"),
            ("Метрики", "6", "аномалии"),
            ("Метрики", "7", "тренд и карточка модели"),
            ("Инструменты", "c", "проверка конфига"),
            ("Инструменты", "d", "diff с последним бэкапом"),
            ("Инструменты", "t", "установить тег модели"),
            ("Инструменты", "f", "модели по тегу"),
            ("Инструменты", "u", "проверить обновление"),
            ("Инструменты", "n", "тест уведомлений"),
            ("Выход", "q", "выйти"),
        ]
        render_menu(items)
        answer = _ask(cy("  выбор: "))
        if answer is None:
            break
        choice = answer.strip().lower()

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
                    _, _, cfg_models = load_config()
                    new = [m for m in live if m not in cfg_models]
                    gone = [m for m in cfg_models if m not in live]
                else:
                    print(r(msg))

        elif choice == "2" and gone:
            picked = fzf_multi(gone, "Tab - выбрать, Enter - подтвердить, Esc - отмена",
                               "убрать> ")
            if picked:
                print(f"  действие: {c('c', '1')} закомментировать · "
                      f"{c('d', '1')} удалить · Enter отмена")
                answer = _ask(cy("  выбор: "))
                if answer is None:
                    break
                act = answer.strip().lower()
                if act in ("c", "d"):
                    ok, msg = apply_edits(
                        adds=[], comment_out=picked if act == "c" else [],
                        deletes=picked if act == "d" else [],
                        note_date=datetime.now().strftime("%d.%m.%Y"))
                    if ok:
                        verb = "закомментировано" if act == "c" else "удалено"
                        print(g(f"{verb} {len(picked)}, бэкап: {msg}"))
                        _, _, cfg_models = load_config()
                        new = [m for m in live if m not in cfg_models]
                        gone = [m for m in cfg_models if m not in live]
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

        elif choice == "5":
            metrics = load_metrics()
            print_stats(metrics)
            print_top(metrics, n=10)

        elif choice == "6":
            print_anomalies(load_metrics())

        elif choice == "7":
            mid = _ask(cy("  модель: "))
            if mid is not None and mid.strip():
                mid = mid.strip()
                metrics = load_metrics()
                if mid in metrics:
                    print_trend(mid)
                    print_info(mid, metrics)
                else:
                    print(y(f"  нет данных по модели {mid}"))

        elif choice == "c":
            for issue in config_check():
                print(f"  {issue}")

        elif choice == "d":
            print(diff_with_last_backup())

        elif choice == "t":
            mid = _ask(cy("  модель: "))
            if mid is None:
                break
            tag = _ask(cy("  тег (пусто — снять): "))
            if tag is not None:
                set_tag(mid.strip(), tag.strip())
                print(g(f"  тег '{tag.strip()}' установлен для {mid.strip()}"))

        elif choice == "f":
            tag = _ask(cy("  тег: "))
            if tag is not None:
                print_filtered(live, tag=tag.strip() or None,
                               metrics=load_metrics())

        elif choice == "u":
            try:
                from rb_tui import update as updater
                latest = updater.check_cached()
                print(y(f"  доступна v{latest} (у тебя v{__version__})")
                      if latest else g("  обновлений нет"))
            except Exception as e:
                print(y(f"  проверить не удалось: {e}"))

        elif choice == "n":
            ok = test_notify()
            print(g("  уведомление отправлено") if ok
                  else r(f"  не удалось: {notify_hint()}"))

        else:
            print(y("  нет такого пункта"))

        redraw()

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
        ttft_s = f"{avg_t:.3f}s" if avg_t is not None else "-"
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
    """Бенчмарк модели на нескольких задачах (стриминговый замер)."""
    print(bold(f"  БЕНЧМАРК: {model_id}"))
    rows = bench_model(base, key, model_id)
    print(dim(f"  проверено промптов: {len(rows)}"))
    print_bench_results(rows, model_id)


def _cmd_compare(base, key, model_a, model_b):
    """A/B сравнение двух моделей."""
    results = compare_models(base, key, model_a, model_b)
    print_compare_results(results, model_a, model_b)


def _cmd_speed(base, key, model_id):
    """Замерить tokens/s."""
    tps, err = speed_test(base, key, model_id)
    print_speed_result(model_id, tps, err)


def _cmd_watch(base, key, interval=300, runs=0, budget=None):
    """Режим наблюдения: каждые N секунд обновлять статус порцией моделей."""
    from rb_tui.metrics import load_metrics, model_status

    print(bold("  WATCH MODE"))
    limit = f", {runs} циклов" if runs > 0 else ""
    print(dim(f"  обновление каждые {interval} сек{limit}, Ctrl+C для выхода"))
    print()

    done = 0
    try:
        while runs <= 0 or done < runs:
            done += 1
            live, _, err = fetch_catalog(base, key)
            if live is None:
                print(r(f"  каталог недоступен: {err}"))
                if runs > 0 and done >= runs:
                    break
                time.sleep(interval)
                continue

            results, _throttled = run_probe_cycle(
                base, key, live, budget=budget, progress=False, verbose=False)

            ts = datetime.now().strftime("%H:%M:%S")
            if results is None:
                line = guard.cooldown_status_line() or "пробы на паузе"
                print(f"  [{ts}] {y(line)}")
            elif not results:
                print(f"  [{ts}] {dim('нет моделей для проверки')}")
            else:
                metrics = load_metrics()
                ok = sum(1 for _, s, _, _, _, _, _, _ in results if s == "OK")
                stable = sum(1 for r_ in results if model_status(metrics, r_[0]) == "stable")
                print(f"  [{ts}] {g(str(ok))}/{len(results)} живых, {g(str(stable))} stable")

            if runs > 0 and done >= runs:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  watch остановлен")


if __name__ == "__main__":
    main()
