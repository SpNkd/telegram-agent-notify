# telegram-agent-notify v0.1.2

This patch release fixes the configuration wizard crash that occurred after successful bot validation and before destination discovery.

- Destination discovery now correctly calls Telegram `getUpdates` through a Telegram client.
- Added regression coverage for the discovery path.

The release includes all features from v0.1.1, including explicit local `--insecure-tls` opt-in and corrected `--codex` installer selection.
