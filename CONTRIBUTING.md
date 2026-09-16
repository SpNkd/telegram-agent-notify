# Contributing

Thanks for helping improve `telegram-agent-notify`.

## Development

The runtime has no third-party dependencies. Use Python 3.9 or newer and run:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile src/telegram_notify.py telegram_notify.py scripts/install.py
```

Keep the CLI dependency-free and preserve support for Linux, macOS, and Windows. Changes to configuration or agent behavior should update both the English and Russian README when practical.

## Security

Never include a real bot token, chat ID, private key, corporate CA contents, or private project data in an issue, pull request, test fixture, screenshot, or commit. Report a suspected security issue privately to the repository owner instead of opening a public issue.

The notifier must keep TLS certificate verification enabled, redact tokens from errors, write the config with restricted permissions, and require explicit file uploads.

## Pull requests

Use a focused branch and explain the user-facing behavior, tests, and compatibility impact. Keep changes small enough to review. The CI workflow must pass on all supported operating systems before merge.
