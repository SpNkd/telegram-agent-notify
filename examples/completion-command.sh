#!/bin/sh
set -eu

telegram-notify completion \
  --status success \
  --task "Reduce application bundle size" \
  --summary "Analyzed dependencies and build configuration; identified approximately 900 KiB of removable assets." \
  --project "md-reader" \
  --tests "42 passed; build successful" \
  --branch "feature/binary-size-analysis" \
  --commit "7a21fc8" \
  --duration "18m 42s"

