"""CLI-диспетчер: разбор аргументов и маршрутизация команд."""

import argparse
import os
import sys

from rb_tui import __version__
from rb_tui import console, crash, guard, interactive, paths, utils
from rb_tui import commands
from rb_tui.alerts import (
    build_webhook_payload, notify_anomalies, notify_hint, notify_new_models,
    notify_stable_to_dead, send_webhook, test_notify, webhook_format,
)
from rb_tui.api import api_key, fetch_catalog
from rb_tui.config import config_check, diff_with_last_backup, load_config
from rb_tui.dashboard import serve
from rb_tui.export import export_csv, export_html, export_json
from rb_tui.metrics import (
    load_metrics, prune_history, record_metric, save_metrics,
)
from rb_tui.probe import ProbeThrottled, probe_with_metrics
from rb_tui.render import (
    print_anomalies, print_filtered, print_grouped_by_owner,
    print_history_ascii, print_info, print_lifetime, print_stats, print_test_table,
    print_top, print_trend, render_report,
)
from rb_tui.sync import (
    auto_cleanup, auto_rollback, auto_sync, load_catalog_owned,
    load_prev_catalog, log_auto, save_catalog,
)
from rb_tui.utils import dim, g, prune_backups, r, set_tag, y


def fail(message, code=1):
    """Показать ошибку и выйти, не закрывая окно на Windows мгновенно."""
    print(r(message))
    console.wait_before_exit()
    sys.exit(code)


def _build_parser():
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
    return parser


def _run_probe_command(count, models, handler, *handler_args):
    """Забронировать бюджет, выполнить сценарий и списать только успех."""
    if not commands.reserve_probes(count, models):
        return
    try:
        handler(*handler_args)
    except ProbeThrottled as e:
        commands.handle_throttle(e)
    else:
        guard.commit(count, models)


def main():
    utils.ensure_setup()
    args = _build_parser().parse_args()

    # Перехват падений ставим до любой реальной работы.
    crash.install()

    if args.config:
        paths.set_config_path(args.config)

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

    commands.notify_update_available()

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

    config_path = utils.get_config()
    if not os.path.isfile(config_path):
        print(r(f"конфиг не найден: {config_path}"))
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
        print_info(args.info, load_metrics())
        return

    if args.history:
        print_history_ascii(args.history, load_metrics())
        return

    if args.trend:
        print_trend(args.trend)
        return

    if args.lifetime:
        print_lifetime(load_metrics())
        return

    if args.anomalies:
        print_anomalies(load_metrics())
        return

    if args.stats:
        print_stats(load_metrics())
        return

    if args.top is not None:
        print_top(load_metrics(), n=args.top, sort_by=args.sort)
        return

    if args.json is not None:
        out = export_json(args.json or None)
        print(f"  экспорт: {out}" if args.json else out)
        return

    if args.export_html is not None:
        out = export_html(args.export_html or None)
        print(f"  экспорт: {out}" if args.export_html else out)
        return

    if args.export_csv is not None:
        out = export_csv(args.export_csv or None)
        print(f"  экспорт: {out}" if args.export_csv else out)
        return

    if args.group_by_owner:
        print_grouped_by_owner(load_metrics(), owned=load_catalog_owned())
        return

    if args.tag:
        set_tag(args.tag[0], args.tag[1])
        print(f"  тег '{args.tag[1]}' установлен для {args.tag[0]}")
        return

    if args.serve:
        serve(host=args.serve_host, port=args.serve_port)
        return

    if args.fuzzy:
        commands.cmd_fuzzy(args.fuzzy, metrics=load_metrics())
        return

    if args.filter:
        metrics = load_metrics()
        live, _, err = fetch_catalog(base, key)
        if live is None:
            print(r(f"каталог недоступен: {err}"))
            return
        print_filtered(live, tag=args.filter, metrics=metrics)
        return

    if args.bench:
        _run_probe_command(3, [args.bench], commands.cmd_bench, base, key, args.bench)
        return

    if args.compare:
        _run_probe_command(6, args.compare, commands.cmd_compare,
                           base, key, args.compare[0], args.compare[1])
        return

    if args.speed:
        _run_probe_command(1, [args.speed], commands.cmd_speed, base, key, args.speed)
        return

    if args.webhook:
        metrics = load_metrics()
        payload = build_webhook_payload(metrics, fmt=webhook_format(args.webhook))
        ok = send_webhook(args.webhook, payload)
        print(g("вебхук отправлен") if ok else r("ошибка вебхука"))
        return

    if args.watch:
        commands.cmd_watch(
            base, key, interval=args.watch_interval,
            runs=args.watch_runs, budget=args.probe_budget,
        )
        return

    # ── каталог ──
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
        metrics = record_metric(
            load_metrics(), mid, status, ttft, total, tokens, fp, msg, tts=tts,
        )
        save_metrics(metrics)
        guard.commit(1, [mid])
        tts_s = f"  tts={tts}" if tts is not None else ""
        print(f"  {mid}: {status}  ttft={ttft}{tts_s}  total={total}  tokens={tokens}")
        return

    # ── --sync ──
    if args.sync:
        auto_sync(new, gone, live)
        results, _throttled = commands.run_probe_cycle(
            base, key, live, budget=args.probe_budget, progress=True)
        if results is None:
            return

        metrics = load_metrics()
        ok_count = sum(1 for item in results if item[1] == "OK")
        if results:
            print(f"  {g(f'✅ {ok_count}/{len(results)} доступны')}, метрики сохранены")
        else:
            print(y("  метрики не обновлялись"))

        notify_new_models(new)
        notify_stable_to_dead(metrics)
        notify_anomalies(metrics)
        auto_cleanup(days=30)
        log_auto(f"sync: тест {ok_count}/{len(results)} живых")
        return

    # ── --report / --test / неинтерактивный запуск ──
    if args.report or args.test or not utils.INTERACTIVE:
        render_report(cfg_models, live, new, gone, True, base,
                      prev_date, appeared, disappeared)
        if args.test:
            results, _throttled = commands.run_probe_cycle(
                base, key, live, budget=args.probe_budget)
            if results:
                print_test_table(results, load_metrics())
            elif results is not None:
                print(y("  нет результатов для таблицы"))
        return

    interactive.run(
        base=base, key=key, live=live, new=new, gone=gone, prev_date=prev_date,
        appeared=appeared, disappeared=disappeared, cfg_models=cfg_models,
        probe_budget=args.probe_budget,
    )


if __name__ == "__main__":
    main()
