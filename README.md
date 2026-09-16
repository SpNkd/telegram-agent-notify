# telegram-agent-notify

Small, dependency-free Telegram notifications for Codex CLI, Claude Code, and other coding agents.

The design is intentionally simple: the agent finishes the task, sends one short completion summary, and then returns its normal final response. It does not mirror stdout or send progress for every tool call.

## Install

Requirements: Python 3.9 or newer. No `pip install` and no runtime packages are needed.

Linux/macOS:

```bash
git clone https://github.com/OWNER/telegram-agent-notify.git
cd telegram-agent-notify
./install.sh
```

The installer adds `telegram-notify` to `~/.local/bin` and asks whether to install the Codex and Claude Code skills. If that directory is not on `PATH`, add it to your shell profile or call the launcher by its absolute path.

Windows PowerShell:

```powershell
git clone https://github.com/OWNER/telegram-agent-notify.git
Set-Location telegram-agent-notify
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

On Windows the launcher is placed in `%LOCALAPPDATA%\\telegram-agent-notify\\telegram-notify.cmd`; add that directory to `PATH` or call the launcher by its full path.

For a non-interactive install:

```bash
./install.sh --yes --codex --claude
```

The installer is idempotent. Use `--force` when updating an existing installation. To test it without touching your home directory, use `./install.sh --prefix "/tmp/telegram notify-test" --yes --codex --claude`.

## Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram.
2. Send `/newbot`, choose a name and username, and copy the token.
3. Run `telegram-notify configure`.
4. Paste the token when prompted.
5. Send any message to the new bot and press Enter in the terminal.
6. The setup discovers recent updates, lets you choose the chat, saves the configuration, and sends a test message.

The token is never placed in this repository. Do not paste a real token into shell history, source files, or issue reports.

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

During `configure`, you can choose the sender name, Telegram topic thread, format, maximum length, proxy, timeout, and whether explicit file uploads are allowed.

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
```

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

Failure summary:

```bash
telegram-notify completion \
  --status failure \
  --task "Build release binaries" \
  --error "Linux ARM linking failed." \
  --last-step "cargo build --release"
```

Send a file only when explicitly requested:

```bash
telegram-notify send-file ./report.md --caption "Full report"
```

The command allows text, Markdown, logs, and small reports. It refuses obvious secret filenames such as `.env`, `*.pem`, `*.key`, `id_rsa`, `credentials*`, and `secrets*` unless `--force` is explicitly supplied. It never discovers or uploads files automatically.

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
- No Telegram request is made by the unit test suite.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 telegram_notify.py --help
python3 telegram_notify.py --version
```

The test suite uses fake HTTP openers. A real Telegram token is never needed to run it.

## License

MIT. See [LICENSE](LICENSE).
