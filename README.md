<p align="center">
  <img src="assets/logo.svg" width="88" alt="ReformBoss Catalog">
</p>

# ReformBoss Catalog

[![tests](https://github.com/JeySerYT/rb-tui/actions/workflows/tests.yml/badge.svg)](https://github.com/JeySerYT/rb-tui/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/JeySerYT/rb-tui?include_prereleases&label=release)](https://github.com/JeySerYT/rb-tui/releases)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![license](https://img.shields.io/github/license/JeySerYT/rb-tui)](LICENSE)

CLI and local dashboard for the ReformBoss model catalog.

`rb-tui` reconciles the ReformBoss model catalog with `opencode.json`, carefully checks
model availability, collects TTFT/TTS/TPS, highlights anomalies, and delivers all
of it in the terminal and in a local web dashboard. It runs as a standalone binary
on Linux, macOS, and Windows — no Python needed.

## Contents

- [Features](#features)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Configuration](#configuration)
- [Dashboard](#dashboard)
- [Careful testing](#careful-testing)
- [Bug reports](#bug-reports)
- [Updating](#updating)
- [Development](#development)
- [License](#license)

## Features

- Reconcile the catalog with the config and safely edit `providers.reformboss.models`.
- Checks with a budget, rotation, and cooldown — no mass API polling.
- TTFT, TTS, TPS, success rate, health score, and history in JSONL.
- Anomalies: latency spikes, TPS drops, and `system_fingerprint` changes.
- Desktop notifications and summaries to Slack, Discord, or a generic webhook.
- Local dashboard with search, filters, a model card, and export.
- Standalone binaries and self-updating from GitHub Releases.
- Crash report with a ready-to-fill Issue form — no token baked into the binary.

## Installation

### One command

**Linux and macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/JeySerYT/rb-tui/main/install.sh | sh
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/JeySerYT/rb-tui/main/install.ps1 | iex
```

The installers download the binary, verify sha256 (`sha256sum` or
`shasum -a 256`), and add it to `PATH`. The directory can be overridden with
`RB_TUI_INSTALL_DIR`, the version with `RB_TUI_VERSION`, and the repository with
`RB_TUI_REPO`.

### Manually

Download the archive for your system from the
[Releases](https://github.com/JeySerYT/rb-tui/releases) page:

| Platform | Archive |
|---|---|
| Linux x86_64 | `rb-tui-linux-x86_64.tar.gz` |
| Linux ARM64 | `rb-tui-linux-arm64.tar.gz` |
| macOS Apple Silicon | `rb-tui-darwin-arm64.tar.gz` |
| macOS Intel | `rb-tui-darwin-x86_64.tar.gz` |
| Windows x86_64 | `rb-tui-windows-x86_64.zip` |

Windows on ARM64 uses `windows-x86_64.zip` via x64 emulation.
Extract it and place `rb-tui` (or `rb-tui.exe`) in a directory on `PATH`.

### From source

```bash
git clone https://github.com/JeySerYT/rb-tui
cd rb-tui
pip install -e .
```

> [!NOTE]
> The binaries are not signed. Windows may show SmartScreen — "More info" →
> "Run anyway"; the installer removes the Mark-of-the-Web itself.
> A macOS archive downloaded manually gets quarantined:
> `xattr -d com.apple.quarantine ./rb-tui`. Installing via `curl | sh`
> and `irm | iex` does not set a quarantine.

## Quick start

```bash
rb-tui                 # interactive mode
rb-tui --report        # what's in the catalog and config
rb-tui --test          # check a batch of models
rb-tui --top 10        # top by TTFT
rb-tui --serve         # dashboard at http://127.0.0.1:9090
```

### Interactive mode

`rb-tui` with no arguments opens the main screen: catalog/config reconciliation,
a status line (health, stable/unstable/dead, number of checks), and a grouped menu:

- **Catalog** — add new models, remove missing ones, availability test, summary to the log;
- **Metrics** — summary with a top list, anomalies, trend, and model card;
- **Tools** — config check, diff, tags, filter, update, notifications;
- **q** — quit.

The screen redraws after every action; `Ctrl+C` and `EOF` end the session.

## Commands

Full list: `rb-tui --help`.

### Catalog and config

| Command | What it does |
|---|---|
| `rb-tui --sync` | Reconcile the catalog, update the config, and check a batch |
| `rb-tui --report` | Catalog report |
| `rb-tui --diff` | Diff the config against the latest backup |
| `rb-tui --config-check` | Check JSONC, key, permissions, baseURL, and catalog |
| `rb-tui --config <PATH>` | Specify the config manually |
| `rb-tui --prune-backups [N]` | Delete backups older than N days |

### Checks and metrics

| Command | What it does |
|---|---|
| `rb-tui --test` | Check a batch of models |
| `rb-tui --probe-model <model>` | Probe a single model |
| `rb-tui --probe-budget N` | Batch size per run |
| `rb-tui --probe-reset` | Clear the pause after a protection trip |
| `rb-tui --bench <model>` | Benchmark on 3 tasks |
| `rb-tui --compare <A> <B>` | A/B comparison of models |
| `rb-tui --speed <model>` | Measure tokens/s |

### Analytics

| Command | What it does |
|---|---|
| `rb-tui --top [N]` | Top models; `--sort ttft\|tps\|rate\|combined` |
| `rb-tui --stats` | Summary: statuses and health score |
| `rb-tui --trend <model>` | TTFT/TTS/TPS sparklines |
| `rb-tui --history <model>` | ASCII chart of TTFT |
| `rb-tui --info <model>` | Metrics, fingerprint, last error |
| `rb-tui --anomalies` | Anomalies and fingerprint changes |
| `rb-tui --lifetime` | When a model appeared |
| `rb-tui --fuzzy <query>` | Find and recommend a model |
| `rb-tui --filter <tag>` | Filter by tag |
| `rb-tui --tag <model> <tag>` | Set a tag |
| `rb-tui --group-by-owner` | Group by `owned_by` |
| `rb-tui --prune-metrics [N]` | Delete history older than N days |

### Dashboard and monitoring

| Command | What it does |
|---|---|
| `rb-tui --serve` | Dashboard at `127.0.0.1:9090` |
| `rb-tui --serve-host <host>` | Different address (non-loopback — no authorization) |
| `rb-tui --watch` | Watch every 5 minutes |
| `rb-tui --watch-interval SEC` | Different interval |
| `rb-tui --watch-runs N` | Limit the number of runs |

### Export and notifications

| Command | What it does |
|---|---|
| `rb-tui --json [path]` | Metrics to JSON |
| `rb-tui --export-html [path]` | HTML report |
| `rb-tui --export-csv [path]` | CSV |
| `rb-tui --webhook <URL>` | Summary to Slack, Discord, or generic |
| `rb-tui --test-notify` | Test desktop notifications |

### Maintenance

| Command | What it does |
|---|---|
| `rb-tui --diag` | Diagnostics for a bug report |
| `rb-tui --report-bug [FILE]` | Open an Issue with the saved report |
| `rb-tui --update-check` | Check for a new version |
| `rb-tui --update` | Update the binary |
| `rb-tui --version` | Version |

## Configuration

rb-tui looks for the global OpenCode config the same way OpenCode itself does.

| OS | Config directories | rb-tui cache |
|---|---|---|
| Linux | `$XDG_CONFIG_HOME/opencode`, `~/.config/opencode`, `/etc/opencode` | `~/.config/reformboss-tui` |
| macOS | `~/Library/Application Support/opencode`, `~/.config/opencode`, `/Library/Application Support/opencode` | `~/.config/reformboss-tui` |
| Windows | `%APPDATA%\opencode`, `~/.config/opencode`, `%ProgramData%\opencode` | `%LOCALAPPDATA%\rb-tui` |

The directory is checked for `opencode.jsonc` and `opencode.json` (`.jsonc` takes priority).
If `reformboss` is present only in the other file in the list, that one wins.
Override: `--config <path>`, `RB_TUI_CONFIG`, or `OPENCODE_CONFIG_DIR`.

### Environment variables

| Variable | Meaning |
|---|---|
| `RB_TUI_CONFIG` | Path to the OpenCode config |
| `RB_TUI_REPO` | Update repository, defaults to `JeySerYT/rb-tui` |
| `RB_TUI_UPDATE_TTL` | Update check interval, seconds (`0` — every run) |
| `RB_TUI_NO_UPDATE_CHECK` | `1` — don't check for updates |
| `RB_TUI_NO_CRASH_HOOK` | `1` — disable crash interception |
| `RB_TUI_NO_REPORT_PROMPT` | `1` — don't prompt, just print the link |
| `REFORMBOSS_PROBE_BUDGET` | Models per run |
| `REFORMBOSS_PROBE_DELAY` | Delay between requests, seconds |
| `REFORMBOSS_DAILY_BUDGET` | Daily probe limit |
| `REFORMBOSS_COOLDOWN` | Pause after a protection trip, seconds |

### Metrics history

- `metrics-history.jsonl` — full history, one JSON record per line;
- `metrics-history.json` — the last 200 probes per model for fast queries;
- cache directory — in the table above.

## Dashboard

`rb-tui --serve` starts a local panel. It has search, filters by status,
provider, and tag, sorting, auto-refresh every 30 seconds, and a model card
with sparklines and recent probes. Export: `/export.csv`,
`/export.json`. Endpoints: `/health`, `/api/view`, `/api/metrics`,
`/api/model/<id>`.

## Careful testing

The ReformBoss API treats mass polling as suspicious, so rb-tui:

- checks only models from the live catalog;
- takes a batch of 10 models (`--probe-budget`) in rotation;
- keeps a 3-second pause + random jitter;
- limits the daily budget to 80 requests — including
  `--bench`, `--compare`, and `--speed`;
- stops and pauses for 6 hours on the first protection detection;
  already collected results are kept, and untested models are not marked dead.

## Bug reports

An unhandled error is saved to the cache (the last three reports), secrets
are scrubbed, and the console offers to open an Issue:

```text
[Enter] open an Issue on GitHub with the filled-in report
[v]     show the report
[n]     exit without reporting
```

The Issue form opens in the browser with the fields filled in: no token is baked into
the binary. `rb-tui --diag` prints the same diagnostics without network access,
`rb-tui --report-bug` opens an Issue from the latest report. In pipes and CI
nothing is prompted.

## Updating

```bash
rb-tui --update-check
rb-tui --update
```

The binary checks for a new version on every run (at most once an hour),
verifies sha256, and atomically replaces itself. On Windows, the replacement is applied after
exit. When running from source, `--update` does not work — update via `pip`.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Tests do not access the network: API, probes, and updates are mocked.

```
rb_tui/
├── cli.py              # argparse and routing
├── commands.py         # shared flows: probes, bench, watch
├── interactive.py      # menu when launched with no arguments
├── paths.py            # config and cache per OS
├── config.py           # reading and editing JSONC
├── probe.py            # TTFT, TTS, TPS, bench, compare
├── guard.py            # budget, rotation, cooldown
├── metrics.py          # history, statuses, anomalies
├── render.py           # terminal tables
├── dashboard.py        # HTTP server and HTML
├── dashboard_view.py   # dashboard view-model
├── alerts.py           # notifications and webhooks
├── export.py           # JSON, HTML, CSV
├── sync.py             # synchronization and rollback
├── update.py           # self-update
├── crash.py            # crash report
├── console.py          # UTF-8, ANSI, pause
└── utils.py            # colors, JSONC, atomic writes
```

Build script for the binary: `scripts/build-binary.sh`. A release is a `v*` tag;
the workflow builds five platforms and publishes archives with checksums. Betas
(`*-beta.*`) are marked as pre-releases. The installers live at permanent URLs in
the repository root and are not copied into every release.

## License

MIT — see [LICENSE](LICENSE).
