# rb-tui 🚀

**ReformBoss model catalog manager** — синхронизация, тестирование, бенчмарки, мониторинг и дашборд для моделей ReformBoss.

## Установка

### 1. Одной командой (Python не нужен)

**Linux / macOS:**

```bash
curl -fsSL https://github.com/JeySerYT/rb-tui/releases/latest/download/install.sh | sh
```

**Windows (PowerShell):**

```powershell
irm https://github.com/JeySerYT/rb-tui/releases/latest/download/install.ps1 | iex
```

Оба скрипта скачивают готовый бинарник из GitHub Releases, проверяют sha256
(`sha256sum` или `shasum -a 256` на macOS) и добавляют его в `PATH`.

- Linux/macOS: ставится в `~/.local/bin`, другой каталог —
  `RB_TUI_INSTALL_DIR=/usr/local/bin sh install.sh`
- Windows: ставится в `%LOCALAPPDATA%\rb-tui\bin`, другой каталог —
  `$env:RB_TUI_INSTALL_DIR="D:\tools"; irm ... | iex`
- конкретная версия: `RB_TUI_VERSION=0.5.0-beta.2`
- если репозиторий называется иначе — `RB_TUI_REPO=owner/repo`.

После установки на Windows перезапусти терминал, чтобы обновился `PATH`.
На macOS установщик распознаёт Apple Silicon даже под Rosetta и подсказывает
строку для `~/.zshrc`.

### 2. Готовый бинарник вручную

Если установщик недоступен, со страницы **Releases** скачивается архив под
свою систему:

`rb-tui-linux-x86_64.tar.gz`, `rb-tui-linux-arm64.tar.gz`,
`rb-tui-darwin-arm64.tar.gz`, `rb-tui-darwin-x86_64.tar.gz`,
`rb-tui-windows-x86_64.zip`.

Windows на ARM64 использует `windows-x86_64.zip` через эмуляцию x64 — отдельной
сборки нет, `--update` подставляет её сам.

Распаковать, положить `rb-tui` (или `rb-tui.exe`) в любой каталог из `PATH`.

`rb-tui --update` скачивает новый релиз, сверяет sha256 и заменяет файл.
На Windows замена применяется сразу после выхода — запускать установщик
вручную не нужно.

> [!NOTE]
> Бинарники не подписаны. При первом запуске Windows может показать
> SmartScreen — «Подробнее» → «Выполнить в любом случае»; установщик снимает
> Mark-of-the-Web сам. На macOS архив, скачанный вручную, получает карантин:
> `xattr -d com.apple.quarantine ./rb-tui`. Установка через `curl | sh` и
> `irm | iex` карантин не ставит.

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

При каждом запуске бинарник сам проверяет новую версию и пишет
`↑ доступна новая версия` — сеть дёргается не чаще раза в час, результат
(в том числе неудачная проверка) кешируется в `~/.config/reformboss-tui`
на Linux/macOS или `%LOCALAPPDATA%\rb-tui` на Windows. Отключить проверку:
`RB_TUI_NO_UPDATE_CHECK=1`, изменить интервал: `RB_TUI_UPDATE_TTL` в секундах
(`0` — проверять каждый запуск).

`--update` работает только для установленного бинарника (не для запуска из
исходников), сверяет контрольную сумму из релиза, проверяет, что новый файл
запускается, и только потом атомарно заменяет старый. На Windows замена
применяется сразу после выхода. Другой репозиторий задаётся через `RB_TUI_REPO`.

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
| `rb-tui --config <PATH>` | Указать конфиг вручную (иначе ищется по ОС) |
| `rb-tui --diag` | Диагностика для отчёта об ошибке (без сети) |
| `rb-tui --report-bug [FILE]` | Открыть Issue с сохранённым отчётом о падении |
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
(для dead-моделей — на 24 часа). Уведомления отправляются средствами текущей
ОС: `notify-send` (Linux), `osascript` (macOS), toast через PowerShell
(Windows). `--test-notify` подсказывает, что проверить, если не сработало.

## Где rb-tui ищет конфиг

Путь не зашит под Linux: rb-tui ищет глобальный конфиг OpenCode так же, как
сам OpenCode.

| ОС | Каталог | Кеш rb-tui |
|---|---|---|
| Linux | `$XDG_CONFIG_HOME/opencode`, затем `~/.config/opencode`, `/etc/opencode` | `~/.config/reformboss-tui` |
| macOS | `~/Library/Application Support/opencode`, затем `~/.config/opencode`, `/Library/Application Support/opencode` | `~/.config/reformboss-tui` |
| Windows | `%APPDATA%\opencode`, затем `~/.config/opencode`, `%ProgramData%\opencode` | `%LOCALAPPDATA%\rb-tui` |

Внутри каталога проверяются оба имени — `opencode.jsonc` и `opencode.json`
(`.jsonc` важнее). Если провайдер `reformboss` нашёлся в другом файле из
списка, выигрывает он: иначе правки ушли бы в пустой конфиг.

Переопределение: `rb-tui --config <файл>` или переменная `RB_TUI_CONFIG`.
Если конфиг не найден, rb-tui печатает все проверенные пути и подсказывает
флаг. Каталог можно задать и через `OPENCODE_CONFIG_DIR`, как это делает
сам OpenCode.

## Если rb-tui упал

Любая непредвиденная ошибка превращается в отчёт:

```text
непредвиденная ошибка: UnicodeEncodeError: ...
отчёт: %LOCALAPPDATA%\rb-tui\crash-20261122-183012.log

[Enter] открыть Issue на GitHub с заполненным отчётом
[v]     показать отчёт
[n]     выйти без отчёта
```

Enter открывает в браузере форму `issues/new` с уже заполненными полями
(браузер, а не токен в бинарнике: публичный токен вытащат и забанят).
В отчёт попадают версия, ОС, Python, путь к конфигу, кодировка вывода и хвост
traceback; ключи, `Bearer`, `sk-…`, URL вебхуков и домашний путь вычищаются.
Хранятся три последних отчёта.

- `RB_TUI_NO_REPORT_PROMPT=1` — не задавать вопрос, только напечатать ссылку.
- `RB_TUI_NO_CRASH_HOOK=1` — выключить перехват целиком.
- В пайпах, CI и OpenCode stdin не терминал, поэтому ничего не спрашивается.
- Окно на Windows, запущенное двойным кликом, не закрывается до Enter.
- `rb-tui --diag` печатает ту же диагностику без сети и без конфига;
  `rb-tui --report-bug` открывает Issue по последнему отчёту.

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

133 теста, без сети: пробы, API, конфиг, дашборд и самообновление подменяются
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
├── install.sh              # установщик Linux/macOS (curl | sh)
├── install.ps1             # установщик Windows (irm | iex)
├── packaging/rb-tui.spec   # сборка standalone-бинарника (PyInstaller)
├── scripts/build-binary.sh # локальная сборка бинарника
├── scripts/release_notes.py # заметки релиза из CHANGELOG.md
├── .github/workflows/      # CI: тесты + релизы под 5 платформ
├── tests/                  # автотесты (unittest, без сети)
├── rb_tui/
│   ├── cli.py              # CLI-диспетчер (argparse)
│   ├── paths.py            # Конфиг и кеш OpenCode на разных ОС
│   ├── config.py           # opencode.json (JSONC, правки, diff)
│   ├── console.py          # UTF-8, ANSI и пауза для консоли Windows
│   ├── crash.py            # Отчёт о падении → Issue по шаблону
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
