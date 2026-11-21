#!/usr/bin/env bash
# Extract translatable strings from QML and Python into po/*.ts
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LUPDATE="$(command -v lupdate6 || echo /usr/lib/qt6/bin/lupdate)"
cd "$ROOT"
for lang in cs; do
  "$LUPDATE" -silent -no-obsolete -locations none src/continuity/qml src/continuity/*.py -ts "po/continuity_${lang}.ts"
done
