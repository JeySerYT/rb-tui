# Changelog

## 0.2.0-beta.1 (2026-11-22)

- Полная переработка: из монолитного скрипта в pip-пакет `rb-tui`
- 13 модулей в `rb_tui/` с чётким разделением ответственности
- `--top N` — топ моделей по TTFT
- `--stats` — общая статистика с health score
- `--json` / `--export-html` / `--export-csv` — экспорт метрик
- `--history <model>` — ASCII-график TTFT
- `--diff` — сравнение с последним бэкапом конфига
- `--bench <model>` — бенчмарк на 3 задачах
- `--compare <A> <B>` — A/B сравнение моделей
- `--speed <model>` — замер tokens/s
- Desktop-уведомления о новых/умерших моделях
- `--webhook <URL>` — сводка на Slack/Discord
- `--serve` — HTTP-дашборд на localhost:9090
- `--config-check` — проверка конфига
- `--prune-backups` — удаление старых бэкапов
- Авто-rollback при битом конфиге
- `--fuzzy <query>` — поиск и рекомендация
- `--filter <tag>` / `--tag <model> <tag>` — теги моделей
- `--info <model>` — детальная информация
- `--lifetime` — время жизни моделей
- `--watch` — режим наблюдения
- `--anomalies` — поиск аномалий
- `--group-by-owner` — группировка по провайдеру
- Health score — общий балл провайдера
- Fingerprint модели (system_fingerprint)
- Systemd-таймер: каждый час (раньше раз в день)

## 0.1.0 (2026-10-25)

- Первая версия: монолитный скрипт `reformboss-tui`
- Сверка каталога ReformBoss с opencode.json
- Интерактивный TUI с fzf
- --sync / --report / --test
- TTFT-замеры и история метрик
