# Changelog

All notable changes to rb-tui. The format is based on [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/lang/ru/).

## Unreleased

### Added

- Groups and new items in the interactive menu: metrics overview, anomalies,
  model trend, config check, diff, tags, filters, update, and notifications.
- Quarantine for a corrupted `metrics-history.json`: the file is moved aside to
  `.corrupt-*` instead of being overwritten with an empty data set.
- Masking of webhook tokens in crash reports and command-line arguments.

### Changed

- `CONFIG` now has a single source of truth (`utils.get_config()`); `--config`
  no longer depends on the list of modules that imported it.
- Console and cache directory setup is performed on demand rather than at import.
- JSONC edits work with multiline model entries; block search takes strings and
  comments into account.
- `cli.main()` has been split into `cli.py`, `commands.py`, and `interactive.py`.
- Beta tags are published as pre-releases; installers live at permanent raw URLs
  and obtain the version via the GitHub API.
- The HTTP dashboard serves requests in parallel.

### Fixed

- `system_fingerprint` is extracted from SSE — model substitution detection works again.
- Success rates in alerts and webhooks are displayed as percentages.
- HTML/CSV export escapes data and suppresses formulas.
- The installer aborts the installation when the checksum file is missing.
- The probe budget is deducted only after successful requests.
- Metric timestamps are stored with an offset; old entries are still readable.
- `install.sh`, `install.ps1`, and `--update` work when all releases are pre-releases.

> The version has not been bumped: work continues under `0.6.0-beta.1` and will
> be included in the next prerelease.

## [0.6.0-beta.1] - 2026-11-22

Full Windows and macOS support: the config is located according to OpenCode rules,
the console no longer crashes on cp1251, installation takes a single command,
and errors are reported in Issues using a template.

### Added

#### Config and paths

- OS-specific lookup of the global OpenCode config: `%APPDATA%\opencode` on Windows,
  `~/Library/Application Support/opencode` on macOS, the XDG directory on Linux,
  then `~/.config/opencode` and the machine directory.
- `opencode.jsonc` takes precedence over `opencode.json`; if the `reformboss`
  provider exists only in another file in the list, that file wins.
- Path override: `--config <PATH>` and `RB_TUI_CONFIG`. If no config is found,
  the list of paths checked is printed.
- Cache on Windows: `%LOCALAPPDATA%\rb-tui`.

#### Console

- `rb_tui/console.py`: UTF-8 output with `errors="replace"`, ANSI via
  `SetConsoleMode`, and an Enter pause before the window closes.
- The API key is read as `utf-8-sig` — a BOM from Notepad no longer causes a 401.
- `os.replace` is retried if the file is locked by an antivirus or a second instance.
- Model selection without `fzf`: numbers `1,3,5`, range `2-4`, `all`.

#### Notifications and reports

- Desktop notifications on macOS (`osascript`) and Windows (toast via PowerShell).
- Crash reports: the three most recent `crash-*.log` files, a secrets sanitizer,
  `--diag`, and `--report-bug`.
- A GitHub Issue form with a pre-filled body — no token is baked into the binary.
- The `RB_TUI_NO_REPORT_PROMPT` and `RB_TUI_NO_CRASH_HOOK` variables.
- The `.github/ISSUE_TEMPLATE/bug_report.md` template.

#### Builds

- Intel Mac: `rb-tui-darwin-x86_64.tar.gz` on `macos-15-intel`.

### Changed

- Backups take the config filename into account: `opencode.json` and `opencode.jsonc`.
- `install.sh`: `shasum -a 256` verification, Rosetta detection, and a hint
  for `~/.zshrc`.
- `install.ps1`: removes the Mark-of-the-Web, warns about SmartScreen, and
  reports ARM64.
- Failed update checks are cached; a found version is retained if the current
  one has not changed.
- CI: Ubuntu 3.10/3.12/3.14, Windows, and macOS; smoke tests of `--version` and
  `--diag` for every built binary.

### Fixed

- Emoji no longer crash startup when output is redirected to cp1251.
- `chmod` permission checks are skipped on Windows.
- The Windows window no longer closes immediately after an error.

## [0.5.0-beta.2] - 2026-11-22

Automatic update checks and one-command installation for Windows.

### Added

- On every launch, the standalone binary checks for a new version and prints
  `↑ a new version is available`; the result is cached for an hour
  (`RB_TUI_UPDATE_TTL`, `RB_TUI_NO_UPDATE_CHECK`).
- `install.ps1`: downloads the zip, verifies sha256, unpacks it to
  `%LOCALAPPDATA%\rb-tui\bin`, and adds the directory to `PATH`.
- Release notes are taken from `CHANGELOG.md` rather than auto-generated from commits.

### Changed

- Manual `--update-check` and `--update` queries go directly to GitHub to avoid
  showing a stale version from the cache.

## [0.5.0-beta.1] - 2026-11-22

Honest numbers, full history, and dashboard v2.

### Added

- `--trend <model>` — TTFT/TTS/TPS sparklines across the entire history.
- `--prune-metrics [N]` — history retention, 90 days by default.
- `--sort ttft|tps|rate|combined` for `--top`.
- `--watch-interval`, `--watch-runs`, and passing `--probe-budget` to `--watch`.
- `--test-notify` — diagnostics for desktop notifications.
- `--config-check` verifies the key file, 600 permissions, baseURL, empty model
  names, and divergence from the latest catalog.
- Webhooks: correct payloads for Slack, Discord, and generic, with retries.
- `--update` and `--update-check`: the binary fetches the release from GitHub,
  verifies `sha256`, checks that the new file launches, and atomically replaces
  the old one; the source can be overridden via `RB_TUI_REPO`.
- Dashboard v2: model card with KPIs, sparklines, the last 12 probes, the last
  error, and fingerprint history.
- Filters by provider and tag, labels for errors and fingerprint changes in the table.
- CSV/JSON export from the dashboard: `/export.csv`, `/export.json`.
- `/health` with version and uptime, `/api/model/<id>` for the card.
- A warning when starting the dashboard on a non-loopback host.
- One-command installation: `curl -fsSL .../install.sh | sh`.
- The Linux binary finds the system CA bundle automatically and works on Arch/CachyOS.
- The release workflow runs only after tests pass.

### Changed

- `--bench` (3 requests), `--compare` (6), and `--speed` (1) check and deduct the
  daily budget via the guard — the limit cannot be bypassed with another flag.
- TPS is calculated by a single formula everywhere: `tokens / total`; the terminal
  and dashboard no longer show different numbers.
- `--bench` and `--compare` now use streaming: TTFT, TTS, and TPS instead of full
  response time presented as TTFT.
- Metrics, config, catalog state, tags, and alerts are written atomically
  (`tmp + os.replace`).
- Config edits target `providers.reformboss.models` rather than the first `models`
  block; both `providers` and `provider` are supported.
- The JSONC parser accepts trailing commas before `}` and `]`.
- Full probe history in `metrics-history.jsonl`; the hot tail in
  `metrics-history.json` has been increased to 200 entries per model.
- `system_fingerprint` changes are tracked in `--anomalies`, `--info`, the
  dashboard, and notifications.
- New anomalies: TTS spike, TPS drop, absolute TTFT threshold.
- Health score now takes TPS into account.
- Alert deduplication: 12 hours for anomalies, 24 hours for dead models.
- `--group-by-owner` uses the real `owned_by` value from the catalog.
- Linux x86_64 and Windows builds no longer require AVX.
- CI: `compileall`, package installation, and a smoke test of `rb-tui --version`;
  92 tests.

### Fixed

- Truncated JSON after a crash no longer loses history.
- On Windows, the update is applied immediately after exit — a running `.exe`
  cannot be overwritten in place.

## [0.4.0-beta.1] - 2026-11-22

Streaming metrics and a new dashboard.

### Added

- TTFT is measured from the stream (`stream: true`); TTS (time to second token)
  and TPS have been added.
- The `dashboard_view.py` module: dashboard data is collected separately and
  covered by tests.
- Dashboard rewritten: off-black theme, KPI cards, search, status filters,
  sorting, sticky table.
- Dashboard auto-refresh every 30 seconds via `/api/view`; `/api/metrics` is
  kept for compatibility.
- CSV and HTML export: TTS and TPS have been added.
- `--stats`, `--info`, and the test table display TTS and TPS.

### Changed

- A probe generates a short, predictable response so that TTS and TPS are meaningful.
- If a provider does not support streaming, the request is retried without it.
- Test count is now 52.

## [0.3.0-beta.1] - 2026-11-22

Installation without Python and not only via pip.

### Added

- Standalone binary built with PyInstaller: `packaging/rb-tui.spec`, 12 MB,
  no Python required.
- `install.sh` — one-command installation via `curl … | sh` with sha256 verification.
- GitHub Actions: releases for `linux-x86_64`, `linux-arm64`, `darwin-arm64`,
  `windows-x86_64`.
- GitHub Actions: tests on Python 3.10, 3.12, and 3.14.
- `scripts/build-binary.sh` — local build of a release archive.

### Changed

- README: four installation methods — curl, binary, uv, pip.

## [0.2.0-beta.3] - 2026-11-22

### Added

- Automated tests: 42 `unittest` tests, no network required (guard, probe,
  metrics, export, version).
- `LICENSE` file (MIT).

### Changed

- README: sections on tests and license; the wheel includes `LICENSE`.

### Fixed

- `--version` reports the same version from source and after `pip install`.

## [0.2.0-beta.2] - 2026-11-22

Gentle testing: the tool no longer looks like a mass API polling operation.

### Added

- The `guard.py` module: probe budget, rotation, daily limit, cooldown.
- Probes only for models in the live catalog; missing models are not probed.
- A batch of 10 models per run (`--probe-budget`), rotating to models that have
  not been checked in a long time.
- A 3-second pause plus random jitter between requests.
- Daily limit of 80 probes.
- On `catalog_probe_detected` or `token_concurrency_limit`, the run stops
  immediately and the tool enters a 6-hour cooldown; no more false `dead` results.
- `--probe-model <model>` — probe a single model.
- `--probe-reset` — clear the probe pause.
- Errors are saved in metrics (`msg`) and shown in the test table.

### Fixed

- Installation: correct build backend and version reading after `pip install`.
- `--json`, `--export-html`, and `--export-csv` write to stdout when called
  without an argument.
- The dashboard listens on `127.0.0.1` by default; a clear message is shown when
  the port is in use.
- `--test` in an interactive terminal actually runs the test instead of opening
  the menu.

## [0.2.0-beta.1] - 2026-11-22

### Added

- `--top N` — top models by TTFT.
- `--stats` — overall statistics with a health score.
- `--json`, `--export-html`, `--export-csv` — metric export.
- `--history <model>` — ASCII chart of TTFT.
- `--diff` — comparison with the latest config backup.
- `--bench <model>` — benchmark across 3 tasks.
- `--compare <A> <B>` — A/B comparison of models.
- `--speed <model>` — measure tokens/s.
- Desktop notifications about new and dead models.
- `--webhook <URL>` — summary to Slack or Discord.
- `--serve` — HTTP dashboard on localhost:9090.
- `--config-check` — config validation.
- `--prune-backups` — removal of old backups.
- Automatic rollback when the config is corrupted.
- `--fuzzy <query>` — search and recommendations.
- `--filter <tag>` and `--tag <model> <tag>` — model tags.
- `--info <model>` — detailed information.
- `--lifetime` — model lifetimes.
- `--watch` — watch mode.
- `--anomalies` — anomaly detection.
- `--group-by-owner` — grouping by provider.
- Health score — an overall score for the provider.
- Model fingerprint (`system_fingerprint`).

### Changed

- Complete overhaul: from a monolithic script to the `rb-tui` pip package.
- 13 modules in `rb_tui/` with clear separation of responsibilities.
- The systemd timer runs every hour instead of once a day.

## [0.1.0] - 2026-10-25

### Added

- First release: the monolithic `reformboss-tui` script.
- Reconciliation of the ReformBoss catalog with `opencode.json`.
- Interactive TUI with `fzf`.
- `--sync`, `--report`, `--test`.
- TTFT measurements and metric history.

[unreleased]: https://github.com/JeySerYT/rb-tui/compare/v0.6.0-beta.1...HEAD
[0.6.0-beta.1]: https://github.com/JeySerYT/rb-tui/compare/v0.5.0-beta.2...v0.6.0-beta.1
[0.5.0-beta.2]: https://github.com/JeySerYT/rb-tui/compare/v0.5.0-beta.1...v0.5.0-beta.2
[0.5.0-beta.1]: https://github.com/JeySerYT/rb-tui/compare/v0.4.0-beta.1...v0.5.0-beta.1
[0.4.0-beta.1]: https://github.com/JeySerYT/rb-tui/compare/v0.3.0-beta.1...v0.4.0-beta.1
[0.3.0-beta.1]: https://github.com/JeySerYT/rb-tui/compare/v0.2.0-beta.3...v0.3.0-beta.1
[0.2.0-beta.3]: https://github.com/JeySerYT/rb-tui/compare/v0.2.0-beta.2...v0.2.0-beta.3
[0.2.0-beta.2]: https://github.com/JeySerYT/rb-tui/compare/v0.2.0-beta.1...v0.2.0-beta.2
[0.2.0-beta.1]: https://github.com/JeySerYT/rb-tui/compare/v0.1.0...v0.2.0-beta.1
[0.1.0]: https://github.com/JeySerYT/rb-tui/releases/tag/v0.1.0
