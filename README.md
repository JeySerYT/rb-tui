# rb-tui 🚀

**ReformBoss model catalog manager** — синхронизация, тестирование, бенчмарки, мониторинг и дашборд для моделей ReformBoss.

## Установка

### 1. Одной командой (Linux / macOS, Python не нужен)

```bash
curl -fsSL https://github.com/JeySerYT/rb-tui/releases/latest/download/install.sh | sh
```

Скрипт скачает готовый бинарник из GitHub Releases, проверит sha256 и положит
его в `~/.local/bin`.

- другой каталог: `RB_TUI_INSTALL_DIR=/usr/local/bin sh install.sh`
- конкретная версия: `RB_TUI_VERSION=0.5.0-beta.1 sh install.sh`
- если репозиторий называется иначе — поменяй `RB_TUI_REPO=owner/repo`.

### 2. Готовый бинарник вручную

Со страницы **Releases** скачивается архив под свою систему:

`rb-tui-linux-x86_64.tar.gz`, `rb-tui-linux-arm64.tar.gz`,
`rb-tui-darwin-arm64.tar.gz`, `rb-tui-windows-x86_64.zip`.

Распаковать и положить `rb-tui` в любой каталог из `PATH`.

### Windows

1. Скачай `rb-tui-windows-x86_64.zip` со страницы **Releases**.
2. Распакуй `rb-tui.exe`, например, в `%USERPROFILE%\bin`.
3. Добавь эту папку в `PATH` (Параметры → Система → О системе →
   Дополнительные параметры системы → Переменные среды).
4. Проверь: `rb-tui.exe --version`.

`rb-tui.exe --update` скачивает новый релиз, сверяет sha256 и заменяет файл
сразу после выхода — запускать установщик вручную не нужно.

### 3. Через uv (Python)

```bash
uv tool install git+https://github.com/JeySerYT/rb-tui
```

### 4. Из исходников

```bash
pip install -e .
```

После установки доступна команда `rb-tui` из любого места.

## Обновление

Standalone-бинарник обновляется сам из GitHub Releases:

```bash
rb-tui --update-check   # узнать, есть ли новая версия
rb-tui --update         # скачать, проверить sha256 и заменить бинарник
```

`--update` работает только для установленного бинарника (не для запуска из
исходников), сверяет контрольную сумму из релиза, проверяет, что новый файл
запускается, и только потом атомарно заменяет старый. На Windows закрой
`rb-tui` перед обновлением. Другой репозиторий задаётся через `RB_TUI_REPO`.

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
| `rb-tui --top [N]` | Топ N моделей (по умолчанию по TTFT) |
| `rb-tui --top N --sort ttft\|tps\|rate\|combined` | Топ по выбранной метрике |
| `rb-tui --trend <model>` | Спарклайны TTFT/TTS/TPS по полной истории |
| `rb-tui --stats` | Общая статистика: stable/unstable/dead, health score |
| `rb-tui --info <model>` | Детальная информация: метрики, fingerprint, последняя ошибка |
| `rb-tui --history <model>` | ASCII-график TTFT по горячему хвосту истории |
| `rb-tui --lifetime` | Когда появилась каждая модель |
| `rb-tui --anomalies` | Аномалии: скачки TTFT/TTS, падение TPS/success, смена fingerprint |
| `rb-tui --group-by-owner` | Группировка по реальному `owned_by` из каталога |
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
| `rb-tui --serve-host <host>` | Адрес дашборда (не-loopback — без авторизации, будет предупреждение) |
| `rb-tui --watch` | Режим наблюдения (обновление каждые 5 мин) |
| `rb-tui --watch-interval SEC` | Интервал обновления в `--watch` |
| `rb-tui --watch-runs N` | Ограничить число циклов `--watch` (0 — бесконечно) |

Панель показывает не только TTFT:

- **TTFT** — время до первого токена;
- **TTS** — время до второго токена (видно, как быстро модель «разгоняется»);
- **TPS** — эффективная скорость: сгенерированные токены за всё время ответа;
- **Success** — доля успешных проб, число проверок и дата последней;
- **Health** — сводная оценка провайдера.

В браузере есть поиск по модели, фильтры по статусу, провайдеру и тегу,
сортировка по любой колонке и автообновление каждые 30 секунд через
`/api/view`. Клик по модели открывает карточку: спарклайны TTFT/TTS/TPS,
последние 12 проб, последняя ошибка и история fingerprint. Из панели можно
скачать CSV или JSON (`/export.csv`, `/export.json`). TTFT, TTS и TPS
считаются по стриминговым ответам (`stream: true`); если провайдер не умеет
стриминг, запрос автоматически повторяется обычным и TTS/TPS остаются пустыми.

JSON-эндпоинты: `/health` (версия и uptime), `/api/view`, `/api/metrics`,
`/api/model/<id>`. Экспорт содержит `schema_version` и `tool_version`.

### История метрик

- `~/.config/reformboss-tui/metrics-history.jsonl` — полная история проб
  (одна JSON-запись на строку, по всем моделям);
- `metrics-history.json` — горячий хвост последних 200 проб на модель для
  быстрых запросов и дашборда;
- `rb-tui --prune-metrics [N]` — удалить записи старше N дней (по умолчанию 90).

Смена `system_fingerprint` под тем же именем модели попадает в `--anomalies`,
`--info`, дашборд и уведомления — это сигнал, что провайдер мог подменить
модель.

### Системные

| Команда | Описание |
|---|---|
| `rb-tui --config-check` | Проверить конфиг: JSONC, ключ, права, baseURL, каталог |
| `rb-tui --diff` | Diff с последним бэкапом |
| `rb-tui --prune-backups [N]` | Удалить бэкапы старше N дней |
| `rb-tui --prune-metrics [N]` | Удалить историю метрик старше N дней |
| `rb-tui --test-notify` | Проверить desktop-уведомления |
| `rb-tui --update-check` | Проверить наличие новой версии на GitHub |
| `rb-tui --update` | Обновить бинарник из последнего релиза |
| `rb-tui --version` | Версия |
| `rb-tui --webhook <URL>` | Отправить сводку на вебхук (Slack, Discord, generic) |

### Уведомления

При `--sync` автоматические отправляются desktop-уведомления:
- О новых моделях
- Когда stable-модель стала dead
- Об аномалиях TTFT, TTS, падении TPS и смене fingerprint

Повторные алерты об одной и той же аномалии подавляются на 12 часов
(для dead-моделей — на 24 часа). `--test-notify` проверяет, что
`notify-send` и DBus работают.

## Бережное тестирование (лимиты API)

API ReformBoss считает массовый опрос моделей подозрительным и может временно
заблокировать сессию (`catalog_probe_detected`, `token_concurrency_limit`).
Поэтому `rb-tui` намеренно не устраивает полный перебор:

- проверяются **только модели из живого каталога** (то, что пропало из каталога,
  не зондируется вообще);
- за прогон — **порция 10 моделей** (`--probe-budget`), выбор по ротации:
  сначала те, кого давно не проверяли;
- между запросами пауза **3 секунды + случайный разброс**;
- **суточный лимит 80 запросов**. В него входят не только `--test` и
  `--probe-model`, но и `--bench` (3 запроса), `--compare` (6) и `--speed` (1):
  бюджет проверяется и списывается **до** запросов, поэтому лимит нельзя
  обойти другим флагом;
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

## Тесты

```bash
python3 -m unittest discover -s tests -v
```

120 тестов, без сети: пробы, API, конфиг, дашборд и самообновление подменяются
моками. Дашборд дополнительно проверяется на реальном локальном сервере (порт 0).

## Лицензия

MIT — см. [LICENSE](LICENSE).

## Структура проекта

```
rb-tui/
├── pyproject.toml          # pip-пакет
├── VERSION                 # версия
├── LICENSE                 # MIT
├── README.md               # этот файл
├── CHANGELOG.md
├── install.sh              # установщик одной командой (curl | sh)
├── packaging/rb-tui.spec   # сборка standalone-бинарника (PyInstaller)
├── scripts/build-binary.sh # локальная сборка бинарника
├── .github/workflows/      # CI: тесты + релизы под 4 платформы
├── tests/                  # автотесты (unittest, без сети)
├── rb_tui/
│   ├── cli.py              # CLI-диспетчер (argparse)
│   ├── config.py           # opencode.json (JSONC, правки, diff)
│   ├── api.py              # ReformBoss API
│   ├── probe.py            # Тестирование (TTFT, speed, compare)
│   ├── guard.py            # Защита от лимитов: бюджет, ротация, cooldown
│   ├── metrics.py          # История метрик, JSONL-архив, статусы, аномалии
│   ├── render.py           # Терминальный вывод (таблицы, топы, тренды)
│   ├── sync.py             # Автосинхронизация и rollback
│   ├── alerts.py           # Уведомления (desktop, webhook, дедупликация)
│   ├── export.py           # Экспорт (JSON, HTML, CSV)
│   ├── dashboard.py        # HTTP-сервер и HTML дашборда
│   ├── dashboard_view.py   # Данные для дашборда (тестируемый view-model)
│   ├── update.py           # Самообновление бинарника из GitHub Releases
│   └── utils.py            # Утилиты (цвета, JSONC, атомарная запись)
└── docs/
    └── AGENTS.md
```

## Фичи

- [x] `--top N` — топ по TTFT, TPS, success или combined
- [x] `--trend` — спарклайны TTFT/TTS/TPS
- [x] `--stats` — общая статистика
- [x] `--json` — экспорт в JSON
- [x] `--export-html` — HTML-отчёт
- [x] `--export-csv` — экспорт в CSV
- [x] `--history` — ASCII-график TTFT
- [x] `--diff` — diff с бэкапом
- [x] `--bench` — бенчмарк модели (стриминговый, TTFT/TTS/TPS)
- [x] `--compare` — A/B сравнение (стриминговый)
- [x] `--speed` — тест скорости (tokens/s)
- [x] Desktop-уведомления
- [x] Webhook-уведомления (Slack, Discord, generic)
- [x] Алертинг: TTFT, TTS, TPS, success, fingerprint, с дедупликацией
- [x] `--serve` — HTTP-дашборд
- [x] Стриминговые пробы: TTFT, TTS и TPS
- [x] Дашборд: поиск, фильтры по статусу/провайдеру/тегу, сортировка, автообновление
- [x] Дашборд: карточка модели со спарклайнами и последними пробами
- [x] Дашборд: экспорт CSV/JSON, `/health` с версией и uptime
- [x] Автоочистка бэкапов и истории метрик
- [x] `--config-check` — глубокая проверка конфига
- [x] `--prune-backups`, `--prune-metrics` — ретеншен
- [x] `--test-notify` — диагностика уведомлений
- [x] Авто-rollback при битом конфиге
- [x] Fingerprint модели и алерт на подмену
- [x] `--fuzzy` — поиск модели
- [x] `--filter` — фильтр по тегу
- [x] `--info` — детальная информация
- [x] `--lifetime` — время жизни моделей
- [x] Tagging — ручные теги
- [x] `--watch`, `--watch-interval`, `--watch-runs` — режим наблюдения
- [x] `--anomalies` — поиск аномалий
- [x] Health score — общий балл провайдера
- [x] `--group-by-owner` — группировка по реальному владельцу
- [x] `--webhook` — вебхук сводки
- [x] Атомарная запись метрик, конфига и состояния каталога
