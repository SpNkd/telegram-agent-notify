---
name: telegram-notify
description: Send one concise Telegram notification after a requested coding task is fully complete, especially when the user asks for completion updates or sets notify_on_completion=true. Do not use for per-step progress, routine tool output, or without an explicit notification request/setting.
---

# Telegram completion notification

Use the repository's `telegram-notify` CLI as the delivery layer. The CLI stores credentials outside the repository and uses safe HTML escaping; do not implement Telegram API calls in the agent turn.

## When to trigger

Trigger only when the user explicitly asks for a Telegram notification, asks to be notified after completion, or provides an explicit `notify_on_completion=true` setting. A long-running task by itself is not permission to send an external message.

## Completion workflow

1. Finish the requested work first. Run the relevant tests, builds, or checks and decide whether the task succeeded or failed.
2. Prepare a compact summary, not a transcript. Include only useful metadata that is available: project, task, result or error, tests, branch, commit, changed files, and duration.
3. As the last operational action before the normal final answer, invoke one of these forms:

   ```bash
   telegram-notify completion \
     --status success \
     --task "Short task name" \
     --summary "What was completed" \
     --project "project-name" \
     --tests "pytest: 42 passed; build: OK" \
     --branch "$(git branch --show-current)" \
     --commit "$(git rev-parse --short HEAD)"
   ```

   For failure, use `--status failure` and provide `--error` and, when useful, `--last-step`.

4. Continue with the ordinary final response even if Telegram is unavailable. The CLI treats delivery failure as a warning and returns success by default so notification cannot mask the coding task's outcome.

Do not call the command after each edit, tool call, test, or intermediate milestone. Do not send stdout, full transcripts, secrets, `.env` contents, credentials, private keys, or arbitrary files. Only send a file when the user explicitly names it and the CLI's secret-file guard allows it.

If `telegram-notify` is not on `PATH`, use the installed absolute path or tell the user that setup is required; never ask the user to paste a bot token into the repository. To configure or diagnose the integration, use `telegram-notify configure`, `telegram-notify test`, or `telegram-notify doctor` only when the user requests setup or troubleshooting.

