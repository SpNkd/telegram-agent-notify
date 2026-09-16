# Security policy

Please do not report credentials or exploitable details in a public issue. Contact the repository owner privately with a description, reproduction steps that use redacted data, and the affected version.

The project intentionally keeps Telegram tokens outside the repository, redacts them from errors, uses atomic `0600` config writes on POSIX, keeps TLS verification enabled, and blocks obvious secret filenames during explicit uploads.
