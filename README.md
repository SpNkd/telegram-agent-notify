# telegram-agent-notify

Small, dependency-free Telegram notifications for Codex CLI, Claude Code, and other coding agents.

[![Tests](https://github.com/SpNkd/telegram-agent-notify/actions/workflows/test.yml/badge.svg)](https://github.com/SpNkd/telegram-agent-notify/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Русская версия: [README.ru.md](README.ru.md).

> AI coding agents: if a user asks you to install or use this repository, read [AGENTS.md](AGENTS.md) first.

The design is intentionally simple: the agent finishes the task, sends one short completion summary, and then returns its normal final response. It does not mirror stdout or send progress for every tool call.

## Demo

These screenshots use demo data only; no real bot token or chat is included.

![Example Telegram completion notification](docs/images/telegram-notification.png)

![Example configuration flow](docs/images/configure.png)

The setup wizard discovers a destination from a message sent in the exact group or topic:

![Automatic group and topic discovery](docs/images/destination-discovery.png)

Project overrides keep different repositories on different Telegram routes while preserving a default:

![Default and per-project Telegram routing](docs/images/project-routing.png)

## Install

Requirements: Python 3.9 or newer. No `pip install` and no runtime packages are needed.

Linux/macOS:

```bash
git clone https://github.com/SpNkd/telegram-agent-notify.git
cd telegram-agent-notify
./install.sh
```

The installer adds `telegram-notify` to `~/.local/bin` and asks whether to install the Codex and Claude Code skills. If that directory is not on `PATH`, add it to your shell profile or call the launcher by its absolute path.

Windows PowerShell:

```powershell
git clone https://github.com/SpNkd/telegram-agent-notify.git
Set-Location telegram-agent-notify
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

On Windows the launcher is placed in `%LOCALAPPDATA%\\telegram-agent-notify\\telegram-notify.cmd`; add that directory to `PATH` or call the launcher by its full path.

For a non-interactive install:

```bash
# Codex only
./install.sh --yes --codex

# Both Codex and Claude Code
./install.sh --yes --codex --claude
```

The installer is idempotent. Use `--force` when updating an existing installation. To test it without touching your home directory, use `./install.sh --prefix "/tmp/telegram notify-test" --yes --codex --claude`.

## Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram.
2. Send `/newbot`, choose a name and username, and copy the token.
3. Add the bot to the target group.
4. Run `telegram-notify configure` and paste the token when prompted.
5. The CLI prints a one-time command such as `/start@your_bot TN-ABCD2345`.
6. Send that command directly to the bot, or inside the exact target group/topic.
7. Press Enter in the terminal. The setup discovers the chat and, when applicable, the topic automatically.
8. Confirm the optional settings and let the setup send a test message.

The token is never placed in this repository. Do not paste a real token into shell history, source files, or issue reports.

For group topics, send the one-time command inside the desired topic. The `/start` command is used so Telegram can deliver it even when the bot's privacy mode is enabled; the bot still has to be a member of the group. The wizard only needs this one command in the desired destination.

## Configure and test

```bash
telegram-notify configure
telegram-notify test
telegram-notify status
telegram-notify doctor
telegram-notify disable
telegram-notify enable
```

Configuration is stored outside the repository:

- Linux/macOS: `$XDG_CONFIG_HOME/telegram-notify/config.json`, or `~/.config/telegram-notify/config.json` when `XDG_CONFIG_HOME` is unset.
- Windows: `%APPDATA%\\telegram-notify\\config.json`.

`configure` asks whether the destination is the default for all projects or only the current project. To make the choice explicit:

```bash
# default destination for all projects
telegram-notify configure --default

# destination for the current Git project; `.` is resolved to its repository root
telegram-notify configure --project-dir .
```

Run the second command from the project directory and send the discovery message in that project's group or topic. Each project override stores only its destination; the bot token remains shared in the protected config file. Without a matching project override, notifications use the default destination.

During `configure`, you can choose the sender name, format, maximum length, proxy, timeout, CA bundle, and whether explicit file uploads are allowed. A topic is selected by sending the discovery message in that topic; no manual topic lookup is required.

For an alternate location, set `TELEGRAM_NOTIFY_CONFIG`. Settings resolve in this order: CLI options, environment variables, config file, defaults.

Useful environment variables:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
TELEGRAM_MESSAGE_THREAD_ID
TELEGRAM_NOTIFY_SENDER
TELEGRAM_NOTIFY_ENABLED
TELEGRAM_NOTIFY_FORMAT=HTML|plain
TELEGRAM_NOTIFY_MAX_LENGTH=3900
TELEGRAM_NOTIFY_TIMEOUT=15
TELEGRAM_NOTIFY_PROXY=http://proxy.example:8080
TELEGRAM_NOTIFY_CA_FILE=/path/to/corporate-root-ca.pem
TELEGRAM_NOTIFY_INSECURE_TLS=false
TELEGRAM_NOTIFY_PROJECT_DIR=/path/to/project
```

If macOS or a corporate HTTPS proxy reports `CERTIFICATE_VERIFY_FAILED`, the recommended fix is to export the proxy's root certificate as a PEM bundle and configure it with `telegram-notify configure --ca-file /path/to/corporate-root-ca.pem` or `TELEGRAM_NOTIFY_CA_FILE`. If this is an intentionally trusted local environment and you accept the risk, use the explicit opt-in:

```bash
telegram-notify configure --insecure-tls
```

This persists the choice in the local config. Re-enable verification with `telegram-notify configure --secure-tls`. The insecure mode disables hostname and certificate verification for Telegram HTTPS requests; never use it on an untrusted network.

For the maintainer's already-approved local setup, every `completion` and explicitly requested `send-file` invocation must include the explicit `--insecure-tls` flag from the first attempt. This is not the default for new installations.

If an agent sandbox reports `nodename nor servname provided`, `Name or service not known`, or another DNS resolution error for `api.telegram.org`, the failure happened before Telegram was contacted. Retry the same command once with the host/system network access provided by the agent environment; `--insecure-tls` does not affect DNS. Stop after that retry if the host network is also unavailable.

## Manual usage

Short form:

```bash
telegram-notify "Task complete" "Implemented the API; tests pass."
```

Equivalent explicit form:

```bash
telegram-notify send \
  --title "Task complete" \
  --message "Implemented the API; tests pass."
```

Completion summary for an agent:

```bash
telegram-notify completion \
  --status success \
  --task "Reduce application bundle size" \
  --summary "Removed unused assets and tightened build configuration." \
  --project "md-reader" \
  --tests "42 passed; build successful" \
  --branch "feature/binary-size-analysis" \
  --commit "7a21fc8" \
  --duration "18m 42s"
```

The command automatically uses the project-specific destination when it is run inside a configured Git repository. Use `--project-dir /path/to/project` when the working directory is different.

Failure summary:

```bash
telegram-notify completion \
  --status failure \
  --task "Build release binaries" \
  --error "Linux ARM linking failed." \
  --last-step "cargo build --release"
```

Send a document or image only when explicitly requested:

```bash
telegram-notify send-file ./report.md --caption "Full report"
telegram-notify send-file ./screenshot.png --caption "Screenshot"
```

The command allows documents, Markdown, logs, small reports, and images up to 10 MiB. PNG and JPEG files are sent as Telegram photos with a preview; other formats are sent as documents. Use `--as-document` when an image must remain a downloadable file. It refuses obvious secret filenames such as `.env`, `*.pem`, `*.key`, `id_rsa`, `credentials*`, and `secrets*` unless `--force` is explicitly supplied. It never discovers or uploads files automatically.

## Codex CLI

The installer places the skill at:

```text
~/.agents/skills/telegram-notify/SKILL.md
```

Codex can discover it automatically. You can also invoke it explicitly with `$telegram-notify` or inspect available skills with `/skills`. If a newly installed skill is not visible, restart Codex.

Use this instruction in a task:

```text
Выполни задачу полностью. После завершения отправь через telegram-notify краткое резюме результата.
```

The skill sends one notification after the work and checks finish. It does not replace Codex's ordinary final answer. If Telegram is unavailable, the CLI prints a warning and returns success by default, so the coding task is not reported as failed merely because delivery failed.

Optional generic session-end hook: inspect [integrations/codex/hooks.json](integrations/codex/hooks.json), merge it into `~/.codex/hooks.json`, then review/trust it with `/hooks`. This reports only that a Codex session ended; use the skill for a real task summary.

## Claude Code

The installer places the skill at:

```text
~/.claude/skills/telegram-notify/SKILL.md
```

Claude Code can load it automatically from its description, or you can invoke `/telegram-notify`. Use the same instruction:

```text
Complete the task fully. After it is finished, send a concise summary through telegram-notify.
```

The optional [integrations/claude/settings.fragment.json](integrations/claude/settings.fragment.json) adds a `SessionEnd` command hook. Merge it into `~/.claude/settings.json` only if generic session-end messages are wanted. Do not use a `Stop` hook for the default workflow because `Stop` fires after turns, not only after the complete task.

## Security and failure behavior

- Bot tokens are read from a hidden prompt, environment, or the user config file; they are not hardcoded.
- Config writes are atomic. POSIX config files are set to mode `0600`.
- `status` never prints the token; it shows only `configured (hidden)`.
- API URLs, request bodies, and tokens are not logged. Error text is token-redacted.
- Dynamic message content is HTML-escaped. `plain` mode is available if desired.
- Network/API errors become a warning for ordinary notifications. `test`, `doctor`, and `configure` still return a failing exit code when verification fails.
- TLS certificate verification is enabled by default. A corporate root CA can be supplied explicitly with `--ca-file` or `TELEGRAM_NOTIFY_CA_FILE`; intentionally trusted local environments can opt in to `--insecure-tls`.
- No Telegram request is made by the unit test suite.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 telegram_notify.py --help
python3 telegram_notify.py --version
```

The test suite uses fake HTTP openers. A real Telegram token is never needed to run it.

CI runs the same checks on Ubuntu, macOS, and Windows with Python 3.9–3.13.

## License

MIT. See [LICENSE](LICENSE).
