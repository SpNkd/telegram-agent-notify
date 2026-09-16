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

Do not call the command after each edit, tool call, test, or intermediate milestone. Do not send stdout, full transcripts, secrets, `.env` contents, credentials, private keys, or arbitrary files. Only send a file when the user explicitly names it and the CLI's secret-file guard allows it. If the user explicitly asks for a named document or image, send it with `telegram-notify send-file PATH --caption "..."` as a separate deliberate upload; PNG/JPEG files become photo previews, while other formats are sent as documents. Add `--as-document` when an image must remain a file.

If `telegram-notify` is not on `PATH`, use the installed absolute path or tell the user that setup is required; never ask the user to paste a bot token into the repository. To configure or diagnose the integration, use `telegram-notify configure`, `telegram-notify test`, or `telegram-notify doctor` only when the user requests setup or troubleshooting.

The CLI can use one default Telegram destination and destination overrides per Git project. `telegram-notify configure` discovers a group or forum topic from a message sent in that exact destination; use `configure --project-dir .` for a project-specific route and `configure --default` for the shared fallback. If HTTPS certificate verification fails behind a corporate proxy, configure its PEM root CA with `--ca-file` or `TELEGRAM_NOTIFY_CA_FILE`. An explicitly trusted local environment may opt in to `configure --insecure-tls`; never enable that mode on an untrusted network.

For the maintainer's configured local macOS setup, `--insecure-tls` is an explicitly approved exception. If a completion or explicitly requested file upload fails specifically with `CERTIFICATE_VERIFY_FAILED`, retry the same command once with `--insecure-tls`. Keep this exception local and do not apply it to another user's setup without explicit approval.

If delivery fails before reaching Telegram with a DNS error such as `nodename nor servname provided`, `Name or service not known`, or `Temporary failure in name resolution`, treat it as an agent sandbox restriction. Retry the same command once through the host/system network execution mode available in the environment. `--insecure-tls` does not affect DNS; preserve it on that retry only when the maintainer's approved local exception applies. Do not retry indefinitely.
