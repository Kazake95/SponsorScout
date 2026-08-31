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

# Repair pip if it is in a broken state (e.g. a half-finished self-upgrade
# left pip._internal.operations.build missing). We detect the breakage by
# trying to import the internal module, then delete the truncated package and
# re-bootstrap pip from its bundled wheel via ensurepip.
if ! python3 -c "import pip._internal.operations.build" >/dev/null 2>&1; then
  echo "Repairing broken pip installation…"
  SITE="$(python3 -c 'import site; print(site.getsitepackages()[0])')"
  rm -rf "$SITE/pip" "$SITE"/pip-*.dist-info
  python3 -m ensurepip --upgrade >/dev/null 2>&1 || python3 -m ensurepip >/dev/null 2>&1 || true
fi
python3 -m pip install -r requirements.txt >/dev/null
python3 -m playwright install chromium >/dev/null || true

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
  --collect-submodules PySide6 \
  sponsorscout/main.py

cp -a "dist/$APP_NAME/"* "$APP_DIR/"

# ── Size reduction: remove caches only ──────────────────────────────────────
# WARNING: Do NOT `strip` the bundled *.so files. PyInstaller ships many Python
# C extensions (numpy/lxml/Pillow/Playwright) whose symbol tables and
# unwind/exception metadata are required at runtime. Stripping them with
# --strip-unneeded produces intermittent SIGSEGV / corrupted-rendering crashes
# that look like a "virus" or "glitchy UI" on the user's machine. We only drop
# caches and obviously-unneeded metadata to stay safe.
echo "Reducing .deb size (safe mode — no binary stripping)…"

# Remove __pycache__ directories and .pyc files (saves 5-15 MB)
find "$APP_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$APP_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

# Remove dist-info metadata directories (saves 5-10 MB)
find "$APP_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true

# Remove unnecessary locale data (saves 2-5 MB)
find "$APP_DIR" -type d -name "locale" -exec rm -rf {} + 2>/dev/null || true

# Remove test directories bundled from packages (saves 5-20 MB)
find "$APP_DIR" -type d \( -name "tests" -o -name "test" -o -name "testing" \) \
  -not -path "*/sponsorscout/*" -exec rm -rf {} + 2>/dev/null || true

# NOTE: The bundled Playwright Chromium (_playwright) is intentionally KEPT so
# JS-rendered career portals work out of the box. Deleting it makes every scan
# fail and the UI appear hung/frozen.
echo "Size reduction complete."

mkdir -p "$BUILD_DIR/usr/bin"
cat > "$BUILD_DIR/usr/bin/sponsorscout" <<'EOL'
#!/bin/sh
# SponsorScout launcher
# The binary lives at /opt/sponsorscout/SponsorScout after copying the
# *contents* of dist/SponsorScout/ into /opt/sponsorscout/.

APP_BIN="/opt/sponsorscout/SponsorScout"

# Verify the binary exists and is executable.
if [ ! -f "$APP_BIN" ]; then
  echo "SponsorScout: ERROR — $APP_BIN not found." >&2
  echo "  The .deb package may not have installed correctly." >&2
  echo "  Try reinstalling:  sudo dpkg --purge sponsorscout && sudo dpkg -i sponsorscout_*.deb" >&2
  exit 1
fi
if [ ! -x "$APP_BIN" ]; then
  echo "SponsorScout: ERROR — $APP_BIN is not executable." >&2
  echo "  Try:  sudo chmod +x $APP_BIN" >&2
  exit 1
fi

# Ensure the Playwright browser binary directory exists.
# Users need to run:  python3 -m playwright install chromium
# (once, or let the app download it at first launch).
if [ -z "$PLAYWRIGHT_BROWSERS_PATH" ]; then
  export PLAYWRIGHT_BROWSERS_PATH="${HOME}/.cache/ms-playwright"
fi

exec "$APP_BIN" "$@"
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
# Update desktop database and icon cache
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi

# Auto-install Playwright Chromium so SPA career portals work out of the box.
# This runs once after package install; it's ~150 MB and required for
# JavaScript-rendered career pages.
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -n "$PYTHON" ] && "$PYTHON" -c "import playwright" 2>/dev/null; then
  echo "SponsorScout: installing Playwright Chromium browser (one-time, ~150 MB)…"
  "$PYTHON" -m playwright install chromium >/dev/null 2>&1 || true
fi

exit 0
EOL
chmod 755 "$DEBIAN_DIR/postinst"

cat > "$DEBIAN_DIR/postrm" <<'EOL'
#!/bin/sh
set -e

# ── Kill any running SponsorScout process before removing files ──────────────
# This prevents file locks and orphaned processes, matching the Windows
# installer behavior (taskkill /f /im SponsorScout.exe).
for sig in TERM KILL; do
  pids=$(pgrep -x "SponsorScout" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "SponsorScout: stopping running instance(s) (SIG$sig)…"
    # shellcheck disable=SC2086
    kill -s "$sig" $pids 2>/dev/null || true
    sleep 1
  fi
done

# ── Remove generated app data from the install directory ─────────────────────
APP_DIR="/opt/sponsorscout"
if [ -d "$APP_DIR" ]; then
  rm -rf "$APP_DIR"
fi

# ── Remove per-user SponsorScout configuration and Playwright browser cache ──
# Iterates over all user home directories to ensure complete cleanup,
# matching the Windows installer which removes {userappdata}\SponsorScout,
# {localappdata}\SponsorScout, and {localappdata}\ms-playwright.
for USER_HOME in "/root" "$HOME" /home/*; do
  # Remove user config/data directory
  if [ -d "$USER_HOME/.sponsorscout" ]; then
    rm -rf "$USER_HOME/.sponsorscout"
  fi
  if [ -f "$USER_HOME/.sponsorscout" ]; then
    rm -f "$USER_HOME/.sponsorscout"
  fi

  # Remove Playwright Chromium browser cache (~150 MB per user)
  PLAYWRIGHT_CACHE="$USER_HOME/.cache/ms-playwright"
  if [ -d "$PLAYWRIGHT_CACHE" ]; then
    echo "SponsorScout: removing Playwright browser cache: $PLAYWRIGHT_CACHE"
    rm -rf "$PLAYWRIGHT_CACHE"
  fi
done

exit 0
EOL
chmod 755 "$DEBIAN_DIR/postrm"

# Verify the binary was copied and is a valid ELF executable.
if [ ! -x "$APP_DIR/$APP_NAME" ]; then
  echo "ERROR: $APP_NAME binary not found in $APP_DIR after PyInstaller build." >&2
  echo "Contents of $APP_DIR:" >&2
  ls -la "$APP_DIR/" >&2
  exit 1
fi

echo "Binary size: $(du -sh "$APP_DIR/$APP_NAME" | cut -f1)"

# dpkg-deb does not require root when the package tree is staged locally.
dpkg-deb --build "$BUILD_DIR" "$DIST_DIR/${PKG_NAME}_${VERSION}_${DEB_ARCH}.deb" >/dev/null

DEB_SIZE=$(du -sh "$DIST_DIR/${PKG_NAME}_${VERSION}_${DEB_ARCH}.deb" | cut -f1)
echo "Built $DIST_DIR/${PKG_NAME}_${VERSION}_${DEB_ARCH}.deb  (${DEB_SIZE})"
