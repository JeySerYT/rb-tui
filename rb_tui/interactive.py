"""Интерактивный режим: запуск rb-tui без аргументов."""

from datetime import datetime

from rb_tui import __version__, utils
from rb_tui import update as updater
from rb_tui.alerts import notify_hint, test_notify
from rb_tui.commands import run_probe_cycle
from rb_tui.config import (
    apply_edits, append_log, config_check, diff_with_last_backup, load_config,
)
from rb_tui.metrics import load_metrics
from rb_tui.render import (
    render_home, render_menu, print_test_table, print_top, print_stats,
    print_info, print_trend, print_anomalies, print_filtered,
)
from rb_tui.utils import cy, dim, g, r, y, fzf_multi, set_tag


def _ask(prompt):
    """Опрос меню; None при EOF/Ctrl+C."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def run(*, base, key, live, new, gone, prev_date, appeared, disappeared,
        cfg_models, probe_budget):
    """Показать главный экран и обрабатывать выбор до выхода."""
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
                print(f"  действие: {utils.c('c', '1')} закомментировать · "
                      f"{utils.c('d', '1')} удалить · Enter отмена")
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
                base, key, live, budget=probe_budget)
            if results:
                print_test_table(results, load_metrics())
                last_results = results
            elif results is not None:
                print(y("  нет результатов для таблицы"))

        elif choice == "4" and (last_results or new or gone):
            ts = datetime.now().strftime("%d.%m.%Y %H:%M")
            lines = [f"── Проверка {ts} ──"]
            if last_results:
                oks = [m for m, s, *_ in last_results if s == "OK"]
                errs = [m for m, s, *_ in last_results if s == "ERR"]
                nos = [m for m, s, *_ in last_results if s == "NO"]
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
