"""python -m rb_tui"""

from rb_tui import crash

# Ставим перехват до импорта CLI: иначе ошибка при импорте останется без отчёта.
crash.install()

from rb_tui.cli import main  # noqa: E402

main()
