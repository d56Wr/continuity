#!/usr/bin/env bash
# Install Continuity for the current user, running straight from this folder (no root needed,
# except to install missing system packages, which it asks about first).
#
#   ./install.sh              check dependencies, build and install
#   ./install.sh --uninstall  remove the launcher, menu entry and icon (settings are kept)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
miss() { printf '  \033[31m✗\033[0m %s\n' "$*"; }
opt()  { printf '  \033[33m–\033[0m %s\n' "$*"; }

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$BIN/continuity" "$BIN/continuity-gmessages" "$APPS/continuity.desktop" "$ICONS/continuity.svg" \
        "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/continuity.desktop"
  update-desktop-database "$APPS" 2>/dev/null || true
  bold "Continuity removed."
  echo "Settings and the Google Messages session are still in ~/.config/continuity and ~/.local/share/continuity."
  exit 0
fi

# ------------------------------------------------------------------ dependencies
distro="other"
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  case " ${ID:-} ${ID_LIKE:-} " in
    *" arch "*) distro="arch" ;;
    *" fedora "*) distro="fedora" ;;
  esac
fi

qml_dir() {  # where system QML modules live
  for d in /usr/lib/qt6/qml /usr/lib64/qt6/qml /usr/lib/*-linux-gnu/qt6/qml; do
    [[ -d "$d" ]] && { echo "$d"; return; }
  done
}
QML="$(qml_dir || true)"

# name | check | Arch package | Fedora package | required?
DEPS=(
  "Python 3.11+|python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'|python|python3|yes"
  "PySide6 (Qt 6 for Python)|python3 -c 'import PySide6.QtQuick'|pyside6|python3-pyside6|yes"
  "PyGObject|python3 -c 'import gi'|python-gobject|python3-gobject|yes"
  "Kirigami|test -d '$QML/org/kde/kirigami'|kirigami|kf6-kirigami|yes"
  "KDE Connect|command -v kdeconnectd || test -x /usr/lib/kdeconnectd || test -x /usr/libexec/kdeconnectd|kdeconnect|kde-connect|yes"
  "LayerShellQt (floating windows on Wayland)|test -d '$QML/org/kde/layershell'|layer-shell-qt|layer-shell-qt|no"
  "PipeWire tools (call audio)|command -v pw-loopback|pipewire-audio|pipewire-utils|no"
  "pactl (call audio mute)|command -v pactl|libpulse|pulseaudio-utils|no"
  "Qt Linguist tools (translations)|command -v lrelease6 || command -v lrelease || test -x /usr/lib/qt6/bin/lrelease|qt6-tools|qt6-linguist|no"
  "Go (Google Messages / RCS helper)|command -v go|go|golang|no"
)

bold "Checking dependencies"
missing=()
missing_required=0
for entry in "${DEPS[@]}"; do
  IFS='|' read -r name check arch fedora required <<<"$entry"
  if bash -c "$check" >/dev/null 2>&1; then
    ok "$name"
  else
    if [[ "$required" == yes ]]; then miss "$name"; missing_required=1; else opt "$name (optional)"; fi
    case "$distro" in
      arch) missing+=("$arch") ;;
      fedora) missing+=("$fedora") ;;
    esac
  fi
done

if ((${#missing[@]})); then
  case "$distro" in
    arch) cmd=(sudo pacman -S --needed "${missing[@]}") ;;
    fedora) cmd=(sudo dnf install "${missing[@]}") ;;
    *) cmd=() ;;
  esac
  if ((${#cmd[@]})); then
    echo
    read -r -p "Install the missing packages with '${cmd[*]}'? [Y/n] " answer
    if [[ ! "$answer" =~ ^[Nn] ]]; then
      "${cmd[@]}"
    fi
  elif ((missing_required)); then
    echo
    echo "Install the missing packages with your package manager, then run this script again."
    exit 1
  fi
fi

# ------------------------------------------------------------------ build and install
echo
bold "Installing"
mkdir -p "$BIN" "$APPS" "$ICONS"
if "$ROOT/scripts/build-translations.sh" 2>/dev/null; then ok "translations"; else opt "translations skipped (no lrelease)"; fi
if command -v go >/dev/null; then
  (cd "$ROOT/helper/gmessages" && go build -trimpath -o "$ROOT/build/continuity-gmessages" .)
  install -m755 "$ROOT/build/continuity-gmessages" "$BIN/continuity-gmessages"
  ok "Google Messages helper"
else
  opt "Google Messages helper skipped (no Go): texts come over KDE Connect, without RCS"
fi
cat > "$BIN/continuity" <<LAUNCH
#!/bin/sh
PYTHONPATH="$ROOT/src\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m continuity "\$@"
LAUNCH
chmod +x "$BIN/continuity"
install -m644 "$ROOT/data/continuity.desktop" "$APPS/continuity.desktop"
install -m644 "$ROOT/src/continuity/data/continuity.svg" "$ICONS/continuity.svg"
update-desktop-database "$APPS" 2>/dev/null || true
ok "launcher $BIN/continuity and menu entry"

echo
bold "Done. Start Continuity from the app menu or run: continuity"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "Note: $BIN is not on your PATH." ;; esac
echo "Update later with: git -C \"$ROOT\" pull && \"$ROOT/install.sh\""
