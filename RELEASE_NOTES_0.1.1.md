# telegram-agent-notify v0.1.1

This patch release fixes the installer selection flags and adds an explicit opt-in for local HTTPS environments whose certificate chain is intentionally intercepted or self-signed.

- `./install.sh --yes --codex` now installs only the Codex skill.
- `./install.sh --yes --claude` now installs only the Claude Code skill.
- `telegram-notify configure --insecure-tls` disables TLS certificate and hostname verification only when explicitly requested and persists that local choice.
- `telegram-notify configure --secure-tls` restores certificate verification.
- Added tests and documentation for both behaviors.

TLS verification remains enabled by default. Use the insecure mode only on a trusted local network.
