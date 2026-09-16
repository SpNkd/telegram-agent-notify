# Design

## Decision

`telegram-agent-notify` uses a small Python 3.9+ standard-library core and a single CLI. Python was chosen over Go because this workflow is dominated by HTTPS, JSON, interactive prompts, and multipart upload; the stdlib implementation has no runtime dependency and is easy to inspect or copy into an agent environment. The repository also ships shell, CMD, and PowerShell launchers.

The public interface is:

```text
telegram-notify "Title" "Message"
telegram-notify completion --status success --task "..." --summary "..."
telegram-notify configure | test | status | doctor | enable | disable
telegram-notify send-file REPORT [--caption ...]
```

The positional form is intentionally convenient for agents. The `completion` form is the preferred integration interface because it has explicit fields for task status and coding metadata.

## Configuration and security

The config path is `TELEGRAM_NOTIFY_CONFIG` when set; otherwise it is `$XDG_CONFIG_HOME/telegram-notify/config.json` on POSIX systems and `%APPDATA%\\telegram-notify\\config.json` on Windows. The token is prompted with `getpass`, written only to that file, and never printed. On POSIX, writes are atomic and the file mode is `0600`.

Resolution order is CLI option, environment variable, config file, built-in default. The token and chat can be supplied through `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `TELEGRAM_MESSAGE_THREAD_ID`; additional `TELEGRAM_NOTIFY_*` variables cover ordinary preferences.

Messages use Telegram HTML mode by default, but all dynamic content is escaped as text. Long messages are split at a conservative visible length of 3900 characters. File sending is always explicit, limited to 10 MiB, and rejects obvious secret filenames unless `--force` is supplied.

## Agent integrations

Codex and Claude Code both support the open agent-skills shape: a directory with `SKILL.md` YAML frontmatter and instructions. The two files intentionally share one name, trigger boundary, and CLI contract. The instructions tell the agent to send one summary only after the primary work is complete, then continue with the normal final response.

The integrations also include optional lifecycle hook snippets. They are not installed by default because a lifecycle event does not contain a reliable task summary and may fire when a user merely closes a session. If enabled manually, the hook sends a generic “session ended” message. It is a convenience fallback, not a replacement for the completion skill.

## Codex research notes

The local Codex CLI used during implementation is `codex-cli 0.153.4`. Its help exposes `/skills` and a hook-trust bypass flag; the local binary also contains the current hook runtime. The official documentation confirms:

- skills are discovered from `.agents/skills` in a repository and `~/.agents/skills` for a user;
- a skill requires `SKILL.md` with `name` and `description`;
- lifecycle hooks are loaded from `~/.codex/hooks.json`, repository `.codex/hooks.json`, or inline `[hooks]` tables;
- `SessionEnd` exists, receives `cwd`, transcript/session context, and runs synchronously;
- non-managed hooks require review/trust and can be inspected with `/hooks`.

The project therefore installs the Codex skill to `~/.agents/skills/telegram-notify` and leaves hook installation opt-in.

References: [Codex skills](https://developers.openai.com/codex/skills/), [Codex hooks](https://developers.openai.com/codex/hooks/), [Codex configuration](https://developers.openai.com/codex/config-advanced/).

## Claude Code research notes

The installed Claude Code CLI is `2.1.272`. Official Claude Code documentation confirms that personal skills live in `~/.claude/skills/<name>/SKILL.md`, and hooks are command handlers in JSON settings such as `~/.claude/settings.json`. `SessionEnd` is available, while `Stop` is per-turn and would violate the one-message completion default. The project therefore installs the Claude skill to `~/.claude/skills/telegram-notify` and provides a separate `SessionEnd` fragment for users who explicitly want generic lifecycle notifications.

References: [Claude Code skills](https://code.claude.com/docs/en/slash-commands), [Claude Code hooks](https://code.claude.com/docs/en/hooks), [Claude Code settings](https://code.claude.com/docs/en/settings).

