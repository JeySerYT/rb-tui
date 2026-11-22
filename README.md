<p align="center">
  <img src="assets/logo.svg" width="88" alt="rb-tui">
</p>

# rb-tui

[![tests](https://github.com/JeySerYT/rb-tui/actions/workflows/tests.yml/badge.svg)](https://github.com/JeySerYT/rb-tui/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/JeySerYT/rb-tui?include_prereleases&label=release)](https://github.com/JeySerYT/rb-tui/releases)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![license](https://img.shields.io/github/license/JeySerYT/rb-tui)](LICENSE)

ReformBoss model catalog manager: синхронизация, проверки, метрики и дашборд.

`rb-tui` сверяет каталог моделей ReformBoss с `opencode.json`, бережно проверяет
доступность моделей, собирает TTFT/TTS/TPS, показывает аномалии и отдаёт всё
это в терминале и в локальном веб-дашборде. Работает как standalone-бинарник
на Linux, macOS и Windows — Python не нужен.

## Содержание

- [Возможности](#возможности)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Команды](#команды)
- [Конфигурация](#конфигурация)
- [Дашборд](#дашборд)
- [Бережное тестирование](#бережное-тестирование)
- [Отчёты об ошибках](#отчёты-об-ошибках)
- [Обновление](#обновление)
- [Разработка](#разработка)
- [Лицензия](#лицензия)

## Возможности

- Сверка каталога с конфигом и безопасная правка `providers.reformboss.models`.
- Проверки с бюджетом, ротацией и cooldown — без массового опроса API.
- TTFT, TTS, TPS, success rate, health score и история в JSONL.
- Аномалии: скачки задержек, падение TPS, смена `system_fingerprint`.
- Desktop-уведомления и сводки в Slack, Discord или generic webhook.
- Локальный дашборд с поиском, фильтрами, карточкой модели и экспортом.
- Standalone-бинарники и самообновление из GitHub Releases.
- Отчёт о падении с готовой формой Issue — без токена в бинарнике.

## Установка

### Одной командой

**Linux и macOS:**

```bash
curl -fsSL https://github.com/JeySerYT/rb-tui/releases/latest/download/install.sh | sh
```

**Windows (PowerShell):**

```powershell
irm https://github.com/JeySerYT/rb-tui/releases/latest/download/install.ps1 | iex
```

Установщики скачивают бинарник, проверяют sha256 (`sha256sum` или
`shasum -a 256`) и добавляют его в `PATH`. Каталог можно переопределить через
`RB_TUI_INSTALL_DIR`, версию — через `RB_TUI_VERSION`, репозиторий — через
`RB_TUI_REPO`.

### Вручную

Со страницы [Releases](https://github.com/JeySerYT/rb-tui/releases) скачивается
архив под систему:

| Платформа | Архив |
|---|---|
| Linux x86_64 | `rb-tui-linux-x86_64.tar.gz` |
| Linux ARM64 | `rb-tui-linux-arm64.tar.gz` |
| macOS Apple Silicon | `rb-tui-darwin-arm64.tar.gz` |
| macOS Intel | `rb-tui-darwin-x86_64.tar.gz` |
| Windows x86_64 | `rb-tui-windows-x86_64.zip` |

Windows на ARM64 использует `windows-x86_64.zip` через эмуляцию x64.
Распаковать и положить `rb-tui` (или `rb-tui.exe`) в каталог из `PATH`.

### Из исходников

```bash
git clone https://github.com/JeySerYT/rb-tui
cd rb-tui
pip install -e .
```

> [!NOTE]
> Бинарники не подписаны. Windows может показать SmartScreen — «Подробнее» →
> «Выполнить в любом случае»; установщик снимает Mark-of-the-Web сам.
> Архив для macOS, скачанный вручную, получает карантин:
> `xattr -d com.apple.quarantine ./rb-tui`. Установка через `curl | sh`
> и `irm | iex` карантин не ставит.

## Быстрый старт

```bash
rb-tui                 # интерактивный режим
rb-tui --report        # что в каталоге и конфиге
rb-tui --test          # проверить порцию моделей
rb-tui --top 10        # топ по TTFT
rb-tui --serve         # дашборд на http://127.0.0.1:9090
```

## Команды

Полный список: `rb-tui --help`.

### Каталог и конфиг

| Команда | Что делает |
|---|---|
| `rb-tui --sync` | Сверить каталог, обновить конфиг и проверить порцию |
| `rb-tui --report` | Отчёт о каталоге |
| `rb-tui --diff` | Diff конфига с последним бэкапом |
| `rb-tui --config-check` | Проверить JSONC, ключ, права, baseURL и каталог |
| `rb-tui --config <PATH>` | Указать конфиг вручную |
| `rb-tui --prune-backups [N]` | Удалить бэкапы старше N дней |

### Проверки и метрики

| Команда | Что делает |
|---|---|
| `rb-tui --test` | Проверить порцию моделей |
| `rb-tui --probe-model <model>` | Проверить одну модель |
| `rb-tui --probe-budget N` | Размер порции за прогон |
| `rb-tui --probe-reset` | Снять паузу после срабатывания защиты |
| `rb-tui --bench <model>` | Бенчмарк на 3 задачах |
| `rb-tui --compare <A> <B>` | A/B сравнение моделей |
| `rb-tui --speed <model>` | Замер tokens/s |

### Аналитика

| Команда | Что делает |
|---|---|
| `rb-tui --top [N]` | Топ моделей; `--sort ttft\|tps\|rate\|combined` |
| `rb-tui --stats` | Сводка: статусы и health score |
| `rb-tui --trend <model>` | Спарклайны TTFT/TTS/TPS |
| `rb-tui --history <model>` | ASCII-график TTFT |
| `rb-tui --info <model>` | Метрики, fingerprint, последняя ошибка |
| `rb-tui --anomalies` | Аномалии и смена fingerprint |
| `rb-tui --lifetime` | Когда появилась модель |
| `rb-tui --fuzzy <query>` | Найти и рекомендовать модель |
| `rb-tui --filter <tag>` | Фильтр по тегу |
| `rb-tui --tag <model> <tag>` | Поставить тег |
| `rb-tui --group-by-owner` | Группировка по `owned_by` |
| `rb-tui --prune-metrics [N]` | Удалить историю старше N дней |

### Дашборд и наблюдение

| Команда | Что делает |
|---|---|
| `rb-tui --serve` | Дашборд на `127.0.0.1:9090` |
| `rb-tui --serve-host <host>` | Другой адрес (не-loopback — без авторизации) |
| `rb-tui --watch` | Наблюдение каждые 5 минут |
| `rb-tui --watch-interval SEC` | Другой интервал |
| `rb-tui --watch-runs N` | Ограничить число циклов |

### Экспорт и уведомления

| Команда | Что делает |
|---|---|
| `rb-tui --json [path]` | Метрики в JSON |
| `rb-tui --export-html [path]` | HTML-отчёт |
| `rb-tui --export-csv [path]` | CSV |
| `rb-tui --webhook <URL>` | Сводка в Slack, Discord или generic |
| `rb-tui --test-notify` | Проверить desktop-уведомления |

### Обслуживание

| Команда | Что делает |
|---|---|
| `rb-tui --diag` | Диагностика для отчёта об ошибке |
| `rb-tui --report-bug [FILE]` | Открыть Issue с сохранённым отчётом |
| `rb-tui --update-check` | Проверить новую версию |
| `rb-tui --update` | Обновить бинарник |
| `rb-tui --version` | Версия |

## Конфигурация

rb-tui ищет глобальный конфиг OpenCode так же, как сам OpenCode.

| ОС | Каталоги конфига | Кеш rb-tui |
|---|---|---|
| Linux | `$XDG_CONFIG_HOME/opencode`, `~/.config/opencode`, `/etc/opencode` | `~/.config/reformboss-tui` |
| macOS | `~/Library/Application Support/opencode`, `~/.config/opencode`, `/Library/Application Support/opencode` | `~/.config/reformboss-tui` |
| Windows | `%APPDATA%\opencode`, `~/.config/opencode`, `%ProgramData%\opencode` | `%LOCALAPPDATA%\rb-tui` |

В каталоге проверяются `opencode.jsonc` и `opencode.json` (`.jsonc` важнее).
Если `reformboss` есть только в другом файле из списка, выигрывает он.
Переопределение: `--config <файл>`, `RB_TUI_CONFIG` или `OPENCODE_CONFIG_DIR`.

### Переменные окружения

| Переменная | Значение |
|---|---|
| `RB_TUI_CONFIG` | Путь к конфигу OpenCode |
| `RB_TUI_REPO` | Репозиторий обновлений, по умолчанию `JeySerYT/rb-tui` |
| `RB_TUI_UPDATE_TTL` | Интервал проверки обновлений, секунды (`0` — каждый запуск) |
| `RB_TUI_NO_UPDATE_CHECK` | `1` — не проверять обновления |
| `RB_TUI_NO_CRASH_HOOK` | `1` — выключить перехват падений |
| `RB_TUI_NO_REPORT_PROMPT` | `1` — не спрашивать, только печатать ссылку |
| `REFORMBOSS_PROBE_BUDGET` | Моделей за прогон |
| `REFORMBOSS_PROBE_DELAY` | Пауза между запросами, секунды |
| `REFORMBOSS_DAILY_BUDGET` | Суточный лимит проб |
| `REFORMBOSS_COOLDOWN` | Пауза после срабатывания защиты, секунды |

### История метрик

- `metrics-history.jsonl` — полная история, одна JSON-запись на строку;
- `metrics-history.json` — последние 200 проб на модель для быстрых запросов;
- каталог кеша — в таблице выше.

## Дашборд

`rb-tui --serve` поднимает локальную панель. В ней поиск, фильтры по статусу,
провайдеру и тегу, сортировка, автообновление каждые 30 секунд и карточка
модели со спарклайнами и последними пробами. Экспорт: `/export.csv`,
`/export.json`. Эндпоинты: `/health`, `/api/view`, `/api/metrics`,
`/api/model/<id>`.

## Бережное тестирование

API ReformBoss считает массовый опрос подозрительным, поэтому rb-tui:

- проверяет только модели из живого каталога;
- берёт порцию 10 моделей (`--probe-budget`) по ротации;
- держит паузу 3 секунды + случайный разброс;
- ограничивает суточный бюджет 80 запросами — в него входят также
  `--bench`, `--compare` и `--speed`;
- при первом детекте защиты останавливается и уходит в паузу на 6 часов;
  уже собранные результаты сохраняются, непроверенные модели не помечаются dead.

## Отчёты об ошибках

Необработанная ошибка сохраняется в кеш (три последних отчёта), секреты
вычищаются, а в консоли предлагается открыть Issue:

```text
[Enter] открыть Issue на GitHub с заполненным отчётом
[v]     показать отчёт
[n]     выйти без отчёта
```

Форма Issue открывается в браузере с заполненными полями: токен в бинарник
не вшивается. `rb-tui --diag` печатает ту же диагностику без сети,
`rb-tui --report-bug` открывает Issue по последнему отчёту. В пайпах и CI
ничего не спрашивается.

## Обновление

```bash
rb-tui --update-check
rb-tui --update
```

Бинарник проверяет новую версию при каждом запуске (не чаще раза в час),
сверяет sha256 и атомарно заменяет себя. На Windows замена применяется после
выхода. Из исходников `--update` не работает — обновляйся через `pip`.

## Разработка

```bash
python3 -m unittest discover -s tests -v
```

Тесты не ходят в сеть: API, пробы и обновления подменяются моками.

```
rb_tui/
├── cli.py              # argparse и сценарии
├── paths.py            # конфиг и кеш по ОС
├── config.py           # чтение и правка JSONC
├── probe.py            # TTFT, TTS, TPS, bench, compare
├── guard.py            # бюджет, ротация, cooldown
├── metrics.py          # история, статусы, аномалии
├── render.py           # терминальные таблицы
├── dashboard.py        # HTTP-сервер и HTML
├── dashboard_view.py   # view-model дашборда
├── alerts.py           # уведомления и вебхуки
├── export.py           # JSON, HTML, CSV
├── sync.py             # синхронизация и rollback
├── update.py           # самообновление
├── crash.py            # отчёт о падении
├── console.py          # UTF-8, ANSI, пауза
└── utils.py            # цвета, JSONC, атомарная запись
```

Сборка бинарника: `scripts/build-binary.sh`. Релиз — тег `v*`; workflow
собирает пять платформ и публикует архивы вместе с `install.sh` и `install.ps1`.

## Лицензия

MIT — см. [LICENSE](LICENSE).