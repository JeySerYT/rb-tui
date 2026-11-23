# How to contribute to rb-tui

Thanks for making it to this file. Below is a short path from an idea to an
accepted change.

## What's welcome

- Bug fixes with a test that catches the bug.
- New commands and metrics, as long as they don't bypass guards or increase
  the load on the API.
- Improvements for Windows and macOS: paths, console, installation, notifications.
- Documentation: README, CHANGELOG, error messages.

## What's not accepted

- Bypassing the daily budget, cooldown, or probe rotation.
- Mass polling of the ReformBoss API.
- Cloud dependencies and telemetry: rb-tui stays local.
- Keys, tokens, and other people's personal data in code, tests, and issues.

## Environment

Python 3.10+ is required.

```bash
git clone https://github.com/JeySerYT/rb-tui
cd rb-tui
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Tests don't access the network: the API, probes, and updates are replaced with
mocks. If you add behavior, add a test that fails without the change.

## Style

- PEP 8, 4-space indentation, line length around 88 characters.
- Names and code in English, user-facing messages in Russian.
- No new dependencies without a good reason: the standalone binary shouldn't grow.
- Word errors so it's clear what to do next.

## Commits and pull requests

- One commit per logical change.
- Message format — Conventional Commits: `fix(probe): …`, `feat(cli): …`.
- In the commit body, explain why the change is needed and how it was tested.
- In the PR, fill out the template: what changes, why, and how it was tested.
- Before submitting, update CHANGELOG if the change is user-visible.

## Security

Don't open a public issue about a vulnerability. The instructions are in
[SECURITY.md](SECURITY.md).

## Code of conduct

By participating in the project, you agree to the [code of conduct](CODE_OF_CONDUCT.md).
