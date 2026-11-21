#!/usr/bin/env bash
# Install a launcher that runs Continuity straight from this source tree (no root needed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$HOME/.local/bin"; APPS="$HOME/.local/share/applications"; ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$BIN" "$APPS" "$ICONS"
"$ROOT/scripts/build-translations.sh" || echo "translations skipped (lrelease6 not found)"
if command -v go >/dev/null; then
  (cd "$ROOT/helper/gmessages" && go build -trimpath -o "$ROOT/build/continuity-gmessages" .)
  install -m755 "$ROOT/build/continuity-gmessages" "$BIN/continuity-gmessages"
else
  echo "Go not found: Google Messages (RCS) support skipped"
fi
cat > "$BIN/continuity" <<LAUNCH
#!/bin/sh
PYTHONPATH="$ROOT/src\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m continuity "\$@"
LAUNCH
chmod +x "$BIN/continuity"
install -m644 "$ROOT/data/continuity.desktop" "$APPS/continuity.desktop"
install -m644 "$ROOT/src/continuity/data/continuity.svg" "$ICONS/continuity.svg"
update-desktop-database "$APPS" 2>/dev/null || true
echo "Installed: $BIN/continuity"
