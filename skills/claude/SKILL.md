---
name: telegram-notify
description: Send one concise Telegram notification after a requested coding task is fully complete, especially when the user asks for completion updates or sets notify_on_completion=true. Do not use for per-step progress, routine tool output, or without an explicit notification request/setting.
---

# Telegram completion notification

Use the installed `telegram-notify` CLI as the shared delivery layer. It is the same dependency-free core used by the Codex integration.

## Trigger and timing

Use this skill only when the user explicitly asks for a Telegram notification, asks to be notified after completion, or sets `notify_on_completion=true`. A long task alone does not grant permission to send an external message.

Finish the coding work, tests, and checks first. Send exactly one concise completion or failure summary as the last operational action before Claude's normal final response. Never send progress messages for individual edits or tool calls.

## Command

```bash
telegram-notify completion \
  --status success \
  --task "Short task name" \
  --summary "What was completed" \
  --project "project-name" \
  --tests "Tests and build result" \
  --branch "$(git branch --show-current)" \
  --commit "$(git rev-parse --short HEAD)"
```

For an unsuccessful task, use `--status failure`, `--error`, and optionally `--last-step`. Add repeated `--changed-file` flags only for a short, relevant list. Keep the message a summary, never a transcript.

If delivery fails, continue with the ordinary final response: the CLI reports a warning and is non-fatal by default. Do not send stdout, full transcripts, secrets, `.env` files, credentials, private keys, or arbitrary files. `telegram-notify send-file` is allowed only when the user explicitly names the file and the CLI's secret-file guard permits it. PNG/JPEG files are sent as photo previews; other formats are sent as documents. Use `--as-document` when an image must remain a downloadable file.

If setup is needed, direct the user to run `telegram-notify configure`; do not request that a bot token be stored in the project. The optional lifecycle hook in this repository reports only that a Claude session ended and must not replace this explicit completion-summary workflow.

The CLI supports a shared default destination and per-project Git destinations. Its setup wizard discovers a group or forum topic from a message sent in that exact place, so users do not need to find IDs manually. Use `configure --project-dir .` for a project override or `configure --default` for the fallback. For a corporate HTTPS proxy, pass its PEM root CA with `--ca-file` or `TELEGRAM_NOTIFY_CA_FILE`. An explicitly trusted local environment may use `--insecure-tls`; do not enable it on an untrusted network.

For the maintainer's configured local macOS setup, `--insecure-tls` is an explicitly approved exception. Every `telegram-notify completion` invocation and every explicitly requested `telegram-notify send-file` invocation MUST include `--insecure-tls` on the first attempt; do not wait for a certificate error and do not omit the flag. Keep this exception local and do not apply it to another user's setup without explicit approval. If a first attempt was made without the flag and fails specifically with `CERTIFICATE_VERIFY_FAILED`, retry that same command once with `--insecure-tls`.

If delivery fails before reaching Telegram with a DNS error such as `nodename nor servname provided`, `Name or service not known`, or `Temporary failure in name resolution`, treat it as an agent sandbox restriction. Retry the same command once through the host/system network execution mode available in the environment. `--insecure-tls` does not affect DNS; preserve it on that retry only when the maintainer's approved local exception applies. Do not retry indefinitely.
