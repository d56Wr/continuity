#!/usr/bin/env bash
# Publish packaging/arch (PKGBUILD + .SRCINFO) to the AUR as continuity-git.
# Needs an AUR account with your SSH public key: https://aur.archlinux.org/account
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/packaging/arch"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# fetch the sources once so makepkg fills in the current pkgver (r<commits>.<hash>)
mkdir "$WORK/build"
cp "$PKG/PKGBUILD" "$WORK/build/"
(cd "$WORK/build" && makepkg -od --noprepare >/dev/null && makepkg --printsrcinfo > .SRCINFO)
cp "$WORK/build/PKGBUILD" "$WORK/build/.SRCINFO" "$PKG/"

git clone -q ssh://aur@aur.archlinux.org/continuity-git.git "$WORK/aur"
cp "$PKG/PKGBUILD" "$PKG/.SRCINFO" "$WORK/aur/"
cd "$WORK/aur"
git add PKGBUILD .SRCINFO
if git diff --cached --quiet; then
  echo "AUR package is already up to date."
  exit 0
fi
git commit -q -m "${1:-Update to $(git -C "$ROOT" rev-parse --short HEAD)}"
git push -q origin HEAD:master
echo "Published: https://aur.archlinux.org/packages/continuity-git"
