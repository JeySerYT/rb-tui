# rb-tui 🚀

**ReformBoss model catalog manager** — синхронизация, тестирование, бенчмарки, мониторинг и дашборд для моделей ReformBoss.

## Установка

```bash
pip install -e /home/jeyseryt/Документы/Project\'s/Скрипты/rb-tui
```

После установки доступна команда `rb-tui` из любого места.

## Использование

### Базовые команды

| Команда | Описание |
|---|---|
| `rb-tui` | Интерактивный режим (TUI) |
| `rb-tui --sync` | Автосинхронизация каталога + бережная проверка порции моделей |
| `rb-tui --report` | Отчёт о каталоге |
| `rb-tui --test` | Проверить порцию моделей (бюджет + ротация) |
| `rb-tui --probe-model <model>` | Проверить одну модель |
| `rb-tui --probe-budget N` | Размер порции за прогон (по умолч. 10) |
| `rb-tui --probe-reset` | Снять паузу проб после срабатывания защиты |

### Аналитика и топы

| Команда | Описание |
|---|---|
| `rb-tui --top [N]` | Топ N моделей по TTFT (по умолч. 10) |
| `rb-tui --stats` | Общая статистика: stable/unstable/dead, health score |
| `rb-tui --info <model>` | Детальная информация о модели |
| `rb-tui --history <model>` | ASCII-график TTFT по истории |
| `rb-tui --lifetime` | Когда появилась каждая модель |
| `rb-tui --anomalies` | Найти аномалии (скачки TTFT, падение success rate) |
| `rb-tui --group-by-owner` | Группировка по провайдеру |
| `rb-tui --fuzzy <query>` | Поиск/рекомендация модели |
| `rb-tui --filter <tag>` | Фильтр по тегу |
| `rb-tui --tag <model> <tag>` | Установить тег модели (coding, design, fast...) |

### Тестирование

| Команда | Описание |
|---|---|
| `rb-tui --bench <model>` | Бенчмарк модели на 3 задачах |
| `rb-tui --compare <A> <B>` | A/B сравнение двух моделей |
| `rb-tui --speed <model>` | Тест скорости генерации (tokens/s) |

### Экспорт

| Команда | Описание |
|---|---|
| `rb-tui --json [path]` | Экспорт метрик в JSON |
| `rb-tui --export-html [path]` | Красивый HTML-отчёт |
| `rb-tui --export-csv [path]` | Экспорт в CSV |

### Дашборд и мониторинг

| Команда | Описание |
|---|---|
| `rb-tui --serve` | HTTP-дашборд на localhost:9090 |
| `rb-tui --watch` | Режим наблюдения (обновление каждые 5 мин) |

### Системные

| Команда | Описание |
|---|---|
| `rb-tui --config-check` | Проверить конфиг на проблемы |
| `rb-tui --diff` | Diff с последним бэкапом |
| `rb-tui --prune-backups [N]` | Удалить бэкапы старше N дней |
| `rb-tui --version` | Версия |
| `rb-tui --webhook <URL>` | Отправить сводку на вебхук |

### Уведомления

При `--sync` автоматические отправляются desktop-уведомления:
- О новых моделях
- Когда stable-модель стала dead
- Об аномалиях TTFT

## Бережное тестирование (лимиты API)

API ReformBoss считает массовый опрос моделей подозрительным и может временно
заблокировать сессию (`catalog_probe_detected`, `token_concurrency_limit`).
Поэтому `rb-tui` намеренно не устраивает полный перебор:

- проверяются **только модели из живого каталога** (то, что пропало из каталога,
  не зондируется вообще);
- за прогон — **порция 10 моделей** (`--probe-budget`), выбор по ротации:
  сначала те, кого давно не проверяли;
- между запросами пауза **3 секунды + случайный разброс**;
- **суточный лимит 80 проб** — предохранитель от частых ручных запусков;
- при первом же детекте защиты прогон **сразу останавливается**, а инструмент
  уходит в **паузу на 6 часов**. Уже собранные реальные результаты сохраняются,
  а модели, до которых очередь не дошла, **не помечаются dead**.

Настройки через переменные окружения: `REFORMBOSS_PROBE_BUDGET`,
`REFORMBOSS_PROBE_DELAY`, `REFORMBOSS_DAILY_BUDGET`, `REFORMBOSS_COOLDOWN`
(секунды). Если сработала защита — `rb-tui --probe-reset` снимает паузу,
`rb-tui --info <model>` покажет последнюю ошибку.

## Автозапуск

Systemd-юзер-таймер запускает `rb-tui --sync` каждый час:

```bash
systemctl --user enable --now rb-tui-sync.timer
```

## Структура проекта

```
rb-tui/
├── pyproject.toml          # pip-пакет
├── VERSION                 # версия
├── README.md               # этот файл
├── CHANGELOG.md
├── rb_tui/
│   ├── cli.py              # CLI-диспетчер (argparse)
│   ├── config.py           # opencode.json (JSONC, правки, diff)
│   ├── api.py              # ReformBoss API
│   ├── probe.py            # Тестирование (TTFT, speed, compare)
│   ├── guard.py            # Защита от лимитов: бюджет, ротация, cooldown
│   ├── metrics.py          # История метрик, статусы, аномалии
│   ├── render.py           # Терминальный вывод (таблицы, топы)
│   ├── sync.py             # Автосинхронизация
│   ├── alerts.py           # Уведомления (desktop, webhook)
│   ├── export.py           # Экспорт (JSON, HTML, CSV)
│   ├── dashboard.py        # HTTP-дашборд
│   └── utils.py            # Утилиты (цвета, JSONC, бэкапы)
└── docs/
    └── AGENTS.md
```

## Фичи (27 шт)

- [x] `--top N` — топ по TTFT
- [x] `--stats` — общая статистика
- [x] `--json` — экспорт в JSON
- [x] `--export-html` — HTML-отчёт
- [x] `--export-csv` — экспорт в CSV
- [x] `--history` — ASCII-график TTFT
- [x] `--diff` — diff с бэкапом
- [x] `--bench` — бенчмарк модели
- [x] `--compare` — A/B сравнение
- [x] `--speed` — тест скорости (tokens/s)
- [x] Desktop-уведомления
- [x] Webhook-уведомления
- [x] Алертинг (аномалии TTFT)
- [x] `--serve` — HTTP-дашборд
- [x] Автоочистка бэкапов
- [x] `--config-check` — проверка конфига
- [x] `--prune-backups` — удаление бэкапов
- [x] Авто-rollback при битом конфиге
- [x] Fingerprint модели (system_fingerprint)
- [x] `--fuzzy` — поиск модели
- [x] `--filter` — фильтр по тегу
- [x] `--info` — детальная информация
- [x] `--lifetime` — время жизни моделей
- [x] Tagging — ручные теги
- [x] `--watch` — режим наблюдения
- [x] `--anomalies` — поиск аномалий
- [x] Health score — общий балл провайдера
- [x] `--group-by-owner` — группировка по провайдеру
- [x] `--webhook` — вебхук сводки
