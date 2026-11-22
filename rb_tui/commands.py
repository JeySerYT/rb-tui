"""Общие сценарии CLI: пробы, бенчмарки, поиск и наблюдение."""

import sys
import time
from datetime import datetime

from rb_tui import __version__, guard
from rb_tui.api import fetch_catalog
from rb_tui.metrics import (
    load_metrics, save_metrics, record_metric,
    model_status, avg_ttft, success_rate,
)
from rb_tui.probe import (
    probe_all, speed_test, compare_models, bench_model, ProbeThrottled,
)
from rb_tui.render import (
    print_top, print_bench_results, print_compare_results, print_speed_result,
)
from rb_tui.utils import g, r, y, dim, bold


def reserve_probes(count, models=None):
    """Проверить cooldown и бюджет до запросов; списание — через commit()."""
    ok, msg = guard.can_reserve(count)
    if not ok:
        prefix = "  ⏸ " if "на паузе" in msg else "  "
        print(y(prefix + msg))
        return False
    return True


def run_probe_cycle(base, key, live, budget=None, progress=False, verbose=True):
    """Цикл проб: cooldown → ротация → порция → стоп на детекте.

    Возвращает (results, throttled); results is None, если пробы на паузе.
    Метрики пишутся только для реально проверенных моделей.
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
        guard.commit(len(results), [item[0] for item in results])

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


def cmd_fuzzy(query, metrics):
    """Поиск модели по имени и рекомендация."""
    query = query.lower()
    results = []
    for mid in metrics:
        if query in mid.lower() or query in mid.replace("-", " ").lower():
            results.append((
                mid, model_status(metrics, mid),
                avg_ttft(metrics, mid), success_rate(metrics, mid),
            ))

    if not results:
        print(dim(f"  по запросу '{query}' ничего не найдено. Показываю топ:"))
        print_top(metrics, n=5)
        return

    print(bold(f"  РЕЗУЛЬТАТЫ ПО ЗАПРОСУ: {query}"))
    print(f"  {'Модель':<34} {'Статус':<9} {'TTFT':<8} {'Success':<8}")
    print(dim("  " + "─" * 65))
    for mid, st, avg_t, rate in sorted(
            results, key=lambda x: avg_ttft(metrics, x[0]) or 999):
        st_badge = g("stable") if st == "stable" else (
            y("unstable") if st == "unstable" else (
                r("dead") if st == "dead" else dim("?")))
        ttft_s = f"{avg_t:.3f}s" if avg_t is not None else "-"
        rate_s = f"{rate}%" if rate is not None else "-"
        print(f"  {mid:<34} {st_badge:<9} {ttft_s:<8} {rate_s:<8}")

    rec = [m for m, s, _, rate in results if s == "stable" and rate and rate >= 80]
    if not rec:
        rec = [m for m, _, _, _ in results]
    if rec:
        best = min(rec, key=lambda m: (avg_ttft(metrics, m) or 999))
        print(f"\n  {g('→ рекомендуем:')} {bold(best)} (TTFT {avg_ttft(metrics, best)}s)")


def cmd_bench(base, key, model_id):
    """Бенчмарк модели на нескольких задачах."""
    print(bold(f"  БЕНЧМАРК: {model_id}"))
    rows = bench_model(base, key, model_id)
    print(dim(f"  проверено промптов: {len(rows)}"))
    print_bench_results(rows, model_id)


def cmd_compare(base, key, model_a, model_b):
    """A/B сравнение двух моделей."""
    results = compare_models(base, key, model_a, model_b)
    print_compare_results(results, model_a, model_b)


def cmd_speed(base, key, model_id):
    """Замер tokens/s."""
    tps, err = speed_test(base, key, model_id)
    print_speed_result(model_id, tps, err)


def cmd_watch(base, key, interval=300, runs=0, budget=None):
    """Обновлять статус порцией моделей каждые N секунд."""
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
                ok = sum(1 for item in results if item[1] == "OK")
                stable = sum(1 for item in results
                             if model_status(metrics, item[0]) == "stable")
                print(f"  [{ts}] {g(str(ok))}/{len(results)} живых, {g(str(stable))} stable")

            if runs > 0 and done >= runs:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  watch остановлен")
