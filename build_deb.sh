#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

APP_NAME="SponsorScout"
PKG_NAME="sponsorscout"
DEB_ARCH="amd64"
VERSION="$(python3 - <<'PY'
from pathlib import Path
import re
text = Path('pyproject.toml').read_text(encoding='utf-8')
m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
if not m:
    raise SystemExit('Unable to read version from pyproject.toml')
print(m.group(1))
PY
)"

BUILD_DIR=".build/deb"
DIST_DIR="dist"
APP_DIR="$BUILD_DIR/opt/$PKG_NAME"
DEBIAN_DIR="$BUILD_DIR/DEBIAN"

need() {
    command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}

need python3
need dpkg-deb

python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install -r requirements.txt pyinstaller >/dev/null
python3 -m playwright install chromium >/dev/null || true
python3 -m pytest -q

rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$APP_DIR" "$DEBIAN_DIR" "$DIST_DIR"

python3 -m PyInstaller \
  --clean \
  --noconfirm \
  --windowed \
  --onedir \
  --name "$APP_NAME" \
  --collect-data sponsorscout \
  --collect-submodules sponsorscout \
  --collect-submodules playwright \
  --collect-submodules google \
  --collect-submodules google.generativeai \
  --collect-submodules openai \
  --hidden-import google.generativeai \
  --hidden-import openai \
  sponsorscout/main.py

cp -a "dist/$APP_NAME/"* "$APP_DIR/"

# Bundle Playwright's Chromium so JS-rendered career pages work out of the box.
# Without this, the installed app gets 0 jobs from all SPA career portals
# because Playwright can't find the browser binary.
PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-${HOME}/.cache/ms-playwright}"
if [ -d "$PLAYWRIGHT_BROWSERS_PATH" ]; then
  CHROMIUM_DIR=$(find "$PLAYWRIGHT_BROWSERS_PATH" -maxdepth 1 -name "chromium*" -type d | head -1)
  if [ -n "$CHROMIUM_DIR" ]; then
    mkdir -p "$APP_DIR/_playwright"
    cp -a "$CHROMIUM_DIR" "$APP_DIR/_playwright/"
    echo "Bundled Chromium from $CHROMIUM_DIR"
  else
    echo "WARNING: No Chromium directory found in $PLAYWRIGHT_BROWSERS_PATH" >&2
  fi
else
  echo "WARNING: Playwright browsers cache not found at $PLAYWRIGHT_BROWSERS_PATH" >&2
fi

mkdir -p "$BUILD_DIR/usr/bin"
cat > "$BUILD_DIR/usr/bin/sponsorscout" <<'EOL'
#!/bin/sh
# Fix B-1: PyInstaller --onedir --name=SponsorScout lays out
#     dist/SponsorScout/{SponsorScout (binary) + support files}
# We copy the *contents* of dist/SponsorScout/ into /opt/sponsorscout/, so
# the binary lives at /opt/sponsorscout/SponsorScout (not nested in another
# SponsorScout/ dir). Previous version pointed at
# /opt/sponsorscout/SponsorScout/SponsorScout which did not exist.
# Point Playwright at the bundled Chromium binary so JS-rendered
# career pages work on the installed system without a separate install step.
export PLAYWRIGHT_BROWSERS_PATH=/opt/sponsorscout/_playwright
exec /opt/sponsorscout/SponsorScout "$@"
EOL
chmod 755 "$BUILD_DIR/usr/bin/sponsorscout"

mkdir -p "$BUILD_DIR/usr/share/applications"
cat > "$BUILD_DIR/usr/share/applications/sponsorscout.desktop" <<EOL
[Desktop Entry]
Version=1.0
Type=Application
Name=SponsorScout
GenericName=Job Sponsorship Finder
Comment=Find visa-sponsoring jobs from official ATS boards
Exec=/usr/bin/sponsorscout
Icon=sponsorscout
Terminal=false
Categories=Office;Network;
Keywords=jobs;visa;sponsorship;careers;
StartupWMClass=SponsorScout
EOL

for size in 16 24 32 48 64 96 128 256 512; do
  src="sponsorscout/data/icons/sponsorscout_${size}.png"
  dst="$BUILD_DIR/usr/share/icons/hicolor/${size}x${size}/apps"
  mkdir -p "$dst"
  cp "$src" "$dst/sponsorscout.png"
done

cat > "$DEBIAN_DIR/control" <<EOL
Package: $PKG_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $DEB_ARCH
Maintainer: SponsorScout <sponsorscout@localhost>
Depends: libc6, libgcc-s1, libstdc++6
Installed-Size: $(du -sk "$BUILD_DIR" | cut -f1)
Description: Job sponsorship search application
 A local desktop app for finding jobs with visa sponsorship signals.
EOL

cat > "$DEBIAN_DIR/postinst" <<'EOL'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
EOL
chmod 755 "$DEBIAN_DIR/postinst"

cat > "$DEBIAN_DIR/postrm" <<'EOL'
#!/bin/sh
set -e
# Remove generated app data from the install directory and any per-user
# SponsorScout configuration directory left behind on uninstall.
APP_DIR="/opt/sponsorscout"
if [ -d "$APP_DIR" ]; then
  rm -rf "$APP_DIR"
fi
for USER_HOME in "/root" "$HOME" /home/*; do
  if [ -d "$USER_HOME/.sponsorscout" ]; then
    rm -rf "$USER_HOME/.sponsorscout"
  fi
  if [ -f "$USER_HOME/.sponsorscout" ]; then
    rm -f "$USER_HOME/.sponsorscout"
  fi
done
exit 0
EOL
chmod 755 "$DEBIAN_DIR/postrm"

# dpkg-deb does not require root when the package tree is staged locally.
dpkg-deb --build "$BUILD_DIR" "$DIST_DIR/${PKG_NAME}_${VERSION}_${DEB_ARCH}.deb" >/dev/null

echo "Built $DIST_DIR/${PKG_NAME}_${VERSION}_${DEB_ARCH}.deb"
