# Changelog

Все заметные изменения проекта. Формат основан на
[Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии — по
[Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [0.6.0-beta.1] - 2026-11-22

Windows и macOS: поиск конфига, консоль, установка и отчёты об ошибках.

### Добавлено

- Поиск конфига OpenCode по ОС: `%APPDATA%\opencode` на Windows,
  `~/Library/Application Support/opencode` на macOS, XDG-каталог на Linux,
  затем `~/.config/opencode` и машинный каталог.
- Поддержка `opencode.jsonc` (важнее `.json`) и выбор файла, в котором есть
  провайдер `reformboss`.
- `--config <PATH>` и `RB_TUI_CONFIG`; если конфиг не найден, печатается
  список проверенных путей.
- Кеш на Windows в `%LOCALAPPDATA%\rb-tui`.
- `rb_tui/console.py`: вывод в UTF-8 с `errors="replace"`, ANSI через
  `SetConsoleMode`, пауза Enter перед закрытием окна.
- Повтор `os.replace`, если файл занят антивирусом или вторым экземпляром.
- Чтение ключа API как `utf-8-sig` — BOM из Блокнота больше не даёт 401.
- Выбор моделей без `fzf`: номера `1,3,5`, диапазон `2-4`, `all`.
- Уведомления macOS (`osascript`) и Windows (toast через PowerShell).
- Отчёты о падении: `crash-*.log` в кеше (три последних), санитайзер секретов,
  форма Issue на GitHub с заполненным телом, `--diag` и `--report-bug`.
- Переменные `RB_TUI_NO_REPORT_PROMPT` и `RB_TUI_NO_CRASH_HOOK`.
- Шаблон `.github/ISSUE_TEMPLATE/bug_report.md`.
- Сборка Intel Mac: `rb-tui-darwin-x86_64.tar.gz` на `macos-15-intel`.

### Изменено

- Бэкапы учитывают имя конфига: `opencode.json` и `opencode.jsonc`.
- `install.sh`: проверка `shasum -a 256`, определение Rosetta, подсказка
  для `~/.zshrc`.
- `install.ps1`: снимает Mark-of-the-Web, предупреждает про SmartScreen,
  сообщает об ARM64.
- Неудачная проверка обновлений кешируется; ранее найденная версия
  сохраняется, если текущая не менялась.
- CI: Ubuntu 3.10/3.12/3.14, Windows и macOS; smoke `--version` и `--diag`
  для каждого собранного бинарника.

### Исправлено

- Эмодзи больше не роняют запуск при перенаправлении вывода в cp1251.
- Проверки прав `chmod` не выполняются на Windows.
- Окно Windows не закрывается мгновенно после ошибки.

## [0.5.0-beta.2] - 2026-11-22

Автопроверка обновлений и установка для Windows одной командой.

### Добавлено

- При каждом запуске standalone-бинарник проверяет новую версию и пишет
  `↑ доступна новая версия`; результат кешируется на час
  (`RB_TUI_UPDATE_TTL`, `RB_TUI_NO_UPDATE_CHECK`).
- `install.ps1`: скачивает zip, проверяет sha256, распаковывает
  в `%LOCALAPPDATA%\rb-tui\bin` и добавляет каталог в `PATH`.
- Заметки релиза берутся из `CHANGELOG.md`, а не из автогенерации коммитов.

### Изменено

- Ручные `--update-check` и `--update` обращаются к GitHub напрямую,
  чтобы не показать устаревшую версию из кеша.

## [0.5.0-beta.1] - 2026-11-22

Честные цифры, полная история и дашборд v2.

### Добавлено

- `--trend <model>` — спарклайны TTFT/TTS/TPS по всей истории.
- `--prune-metrics [N]` — ретеншен истории, по умолчанию 90 дней.
- `--sort ttft|tps|rate|combined` для `--top`.
- `--watch-interval`, `--watch-runs` и передача `--probe-budget` в `--watch`.
- `--test-notify` — диагностика desktop-уведомлений.
- `--config-check` проверяет файл ключа, права 600, baseURL, пустые имена
  моделей и расхождение с последним каталогом.
- Webhook: корректные payload для Slack, Discord и generic, с повторами.
- `--update` и `--update-check`: бинарник тянет релиз с GitHub, сверяет
  `sha256`, проверяет запуск нового файла и атомарно заменяет старый;
  источник переопределяется через `RB_TUI_REPO`.
- Дашборд v2: карточка модели с KPI, спарклайнами, последними 12 пробами,
  последней ошибкой и историей fingerprint.
- Фильтры по провайдеру и тегу, метки ошибок и смены fingerprint в таблице.
- Экспорт CSV/JSON из панели: `/export.csv`, `/export.json`.
- `/health` с версией и uptime, `/api/model/<id>` для карточки.
- Предупреждение при запуске дашборда на не-loopback хосте.
- Установка одной командой: `curl -fsSL .../install.sh | sh`.
- Linux-бинарник сам находит системный CA-бандл и работает на Arch/CachyOS.
- Release-workflow запускается только после зелёных тестов.

### Изменено

- `--bench` (3 запроса), `--compare` (6) и `--speed` (1) проверяют и списывают
  суточный бюджет через guard — лимит нельзя обойти другим флагом.
- TPS считается по одной формуле везде: `tokens / total`; терминал и дашборд
  больше не показывают разные числа.
- `--bench` и `--compare` переведены на стриминг: TTFT, TTS и TPS вместо
  полного времени ответа под видом TTFT.
- Метрики, конфиг, состояние каталога, теги и алерты пишутся атомарно
  (`tmp + os.replace`).
- Правки конфига целятся в `providers.reformboss.models`, а не в первый блок
  `models`; поддержаны `providers` и `provider`.
- JSONC-парсер принимает висячие запятые перед `}` и `]`.
- Полная история проб в `metrics-history.jsonl`; горячий хвост в
  `metrics-history.json` увеличен до 200 записей на модель.
- Смена `system_fingerprint` отслеживается в `--anomalies`, `--info`,
  дашборде и уведомлениях.
- Новые аномалии: скачок TTS, падение TPS, абсолютный порог TTFT.
- Health score учитывает TPS.
- Дедупликация алертов: 12 часов для аномалий, 24 часа для dead-моделей.
- `--group-by-owner` использует реальный `owned_by` из каталога.
- Сборки Linux x86_64 и Windows не требуют AVX.
- CI: `compileall`, установка пакета и smoke `rb-tui --version`; 92 теста.

### Исправлено

- Обрезанный JSON при сбое больше не теряет историю.
- На Windows обновление применяется сразу после выхода — запущенный `.exe`
  нельзя перезаписать на месте.

## [0.4.0-beta.1] - 2026-11-22

Стриминговые метрики и новая панель.

### Добавлено

- TTFT измеряется по стриму (`stream: true`), добавлены TTS (время до второго
  токена) и TPS.
- Модуль `dashboard_view.py`: данные панели собираются отдельно и покрыты
  тестами.
- Дашборд переписан: off-black тема, KPI-карточки, поиск, фильтры по статусу,
  сортировка, sticky-таблица.
- Автообновление панели каждые 30 секунд через `/api/view`; `/api/metrics`
  сохранён для совместимости.
- Экспорт CSV и HTML: добавлены TTS и TPS.
- `--stats`, `--info` и таблица теста показывают TTS и TPS.

### Изменено

- Проба генерирует короткий предсказуемый ответ, чтобы TTS и TPS были
  осмысленными.
- Если провайдер не поддерживает стриминг, запрос повторяется обычным.
- Тестов стало 52.

## [0.3.0-beta.1] - 2026-11-22

Установка без Python и не только через pip.

### Добавлено

- Standalone-бинарник на PyInstaller: `packaging/rb-tui.spec`, 12 МБ,
  Python не нужен.
- `install.sh` — установка одной командой `curl … | sh` с проверкой sha256.
- GitHub Actions: релизы под `linux-x86_64`, `linux-arm64`, `darwin-arm64`,
  `windows-x86_64`.
- GitHub Actions: тесты на Python 3.10, 3.12 и 3.14.
- `scripts/build-binary.sh` — локальная сборка архива для релиза.

### Изменено

- README: четыре способа установки — curl, бинарник, uv, pip.

## [0.2.0-beta.3] - 2026-11-22

### Добавлено

- Автотесты: 42 теста на `unittest`, без сети (guard, probe, metrics, export,
  version).
- Файл `LICENSE` (MIT).

### Исправлено

- `--version` показывает одну и ту же версию из исходников и после
  `pip install`.

### Изменено

- README: разделы про тесты и лицензию; wheel включает `LICENSE`.

## [0.2.0-beta.2] - 2026-11-22

Бережное тестирование: инструмент больше не выглядит как массовый опрос API.

### Добавлено

- Модуль `guard.py`: бюджет проб, ротация, суточный лимит, cooldown.
- Пробы только по моделям из живого каталога; пропавшие не зондируются.
- Порция 10 моделей за прогон (`--probe-budget`), ротация «кого давно
  не проверяли».
- Пауза 3 секунды + случайный разброс между запросами.
- Суточный лимит 80 проб.
- При `catalog_probe_detected` или `token_concurrency_limit` прогон сразу
  останавливается, инструмент уходит в 6-часовой cooldown; ложных `dead`
  больше нет.
- `--probe-model <model>` — проверить одну модель.
- `--probe-reset` — снять паузу проб.
- Ошибки сохраняются в метриках (`msg`) и видны в таблице теста.

### Исправлено

- Установка: корректный build-backend и чтение версии после `pip install`.
- `--json`, `--export-html` и `--export-csv` без аргумента пишут в stdout.
- Дашборд по умолчанию слушает `127.0.0.1`; понятное сообщение при занятом
  порту.
- `--test` в интерактивном терминале действительно запускает тест, а не меню.

## [0.2.0-beta.1] - 2026-11-22

### Добавлено

- `--top N` — топ моделей по TTFT.
- `--stats` — общая статистика с health score.
- `--json`, `--export-html`, `--export-csv` — экспорт метрик.
- `--history <model>` — ASCII-график TTFT.
- `--diff` — сравнение с последним бэкапом конфига.
- `--bench <model>` — бенчмарк на 3 задачах.
- `--compare <A> <B>` — A/B сравнение моделей.
- `--speed <model>` — замер tokens/s.
- Desktop-уведомления о новых и умерших моделях.
- `--webhook <URL>` — сводка в Slack или Discord.
- `--serve` — HTTP-дашборд на localhost:9090.
- `--config-check` — проверка конфига.
- `--prune-backups` — удаление старых бэкапов.
- Авто-rollback при битом конфиге.
- `--fuzzy <query>` — поиск и рекомендация.
- `--filter <tag>` и `--tag <model> <tag>` — теги моделей.
- `--info <model>` — детальная информация.
- `--lifetime` — время жизни моделей.
- `--watch` — режим наблюдения.
- `--anomalies` — поиск аномалий.
- `--group-by-owner` — группировка по провайдеру.
- Health score — общий балл провайдера.
- Fingerprint модели (`system_fingerprint`).

### Изменено

- Полная переработка: из монолитного скрипта в pip-пакет `rb-tui`.
- 13 модулей в `rb_tui/` с чётким разделением ответственности.
- Systemd-таймер запускается каждый час вместо раза в день.

## [0.1.0] - 2026-10-25

### Добавлено

- Первая версия: монолитный скрипт `reformboss-tui`.
- Сверка каталога ReformBoss с `opencode.json`.
- Интерактивный TUI с `fzf`.
- `--sync`, `--report`, `--test`.
- TTFT-замеры и история метрик.

[Unreleased]: https://github.com/JeySerYT/rb-tui/compare/v0.6.0-beta.1...HEAD
[0.6.0-beta.1]: https://github.com/JeySerYT/rb-tui/compare/v0.5.0-beta.2...v0.6.0-beta.1
[0.5.0-beta.2]: https://github.com/JeySerYT/rb-tui/compare/v0.5.0-beta.1...v0.5.0-beta.2
[0.5.0-beta.1]: https://github.com/JeySerYT/rb-tui/compare/v0.4.0-beta.1...v0.5.0-beta.1
[0.4.0-beta.1]: https://github.com/JeySerYT/rb-tui/compare/v0.3.0-beta.1...v0.4.0-beta.1
[0.3.0-beta.1]: https://github.com/JeySerYT/rb-tui/compare/v0.2.0-beta.3...v0.3.0-beta.1
[0.2.0-beta.3]: https://github.com/JeySerYT/rb-tui/compare/v0.2.0-beta.2...v0.2.0-beta.3
[0.2.0-beta.2]: https://github.com/JeySerYT/rb-tui/compare/v0.2.0-beta.1...v0.2.0-beta.2
[0.2.0-beta.1]: https://github.com/JeySerYT/rb-tui/compare/v0.1.0...v0.2.0-beta.1
[0.1.0]: https://github.com/JeySerYT/rb-tui/releases