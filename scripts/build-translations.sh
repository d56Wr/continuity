#!/usr/bin/env bash
# Compile po/*.ts into src/continuity/i18n/*.qm
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LRELEASE="$(command -v lrelease6 || command -v lrelease || echo /usr/lib/qt6/bin/lrelease)"
mkdir -p "$ROOT/src/continuity/i18n"
for ts in "$ROOT"/po/*.ts; do
  [ -e "$ts" ] || continue
  "$LRELEASE" -silent "$ts" -qm "$ROOT/src/continuity/i18n/$(basename "${ts%.ts}").qm"
done
