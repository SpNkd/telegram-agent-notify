# Changelog

All notable changes to this project are documented here.

## [0.1.2] - 2026-09-16

- Fixed `configure` destination discovery after successful bot validation by passing a Telegram client to the update lookup.

## [0.1.1] - 2026-09-16

- Fixed explicit `--codex` and `--claude` installer flags so `--yes` does not install the other skill unexpectedly.
- Added an explicit `--insecure-tls` opt-in for trusted local HTTPS interception environments.

## [0.1.0] - 2026-09-16

- Initial public release.
- Dependency-free Telegram CLI for concise completion summaries.
- Interactive bot, group, and topic discovery through Telegram updates.
- Default and per-project destinations.
- Codex CLI and Claude Code skills with optional lifecycle hook snippets.
- Safe config storage, HTML escaping, redacted errors, explicit file sending, and cross-platform installers.
- Unit tests and GitHub Actions coverage for Ubuntu, macOS, and Windows.
