#!/bin/zsh
# Build and install SemSearch:
#   1. create .venv and install Python dependencies (needs Python 3.11+; uses uv if present)
#   2. put the menu-bar app into /Applications/SemSearch.app and the helpers into bin/, compiled
#      with swiftc, or taken from prebuilt/ (the Homebrew package ships them compiled)
#   3. start it at login (LaunchAgent) and link the `ss` command
# Usage: ./install.sh            (run again after pulling updates)
# Testing: SEMSEARCH_APP=/tmp/SemSearch.app SEMSEARCH_SKIP_AGENT=1 ./install.sh
#          builds everything but does not touch /Applications, login items or running apps
set -euo pipefail
cd "$(dirname "$0")"
REPO="$PWD"
APP="${SEMSEARCH_APP:-/Applications/SemSearch.app}"
SKIP_AGENT="${SEMSEARCH_SKIP_AGENT:-}"
LABEL="io.github.kuanlinb.semsearch"
VERSION="$(cat VERSION)"

die() { echo "Error: $*" >&2; exit 1; }
[[ "$(uname -m)" == "arm64" ]] || die "SemSearch needs an Apple silicon Mac (arm64)."
# Without the Command Line Tools, /usr/bin/swiftc is only a stub that offers to install them
have_swiftc() { xcode-select -p >/dev/null 2>&1 && xcrun --find swiftc >/dev/null 2>&1; }
if [[ -f prebuilt/VERSION && "$(cat prebuilt/VERSION)" == "$VERSION" ]]; then
  SWIFT_BIN="$REPO/prebuilt"
else
  have_swiftc || die "The Xcode Command Line Tools are needed to build the app. Run: xcode-select --install"
  SWIFT_BIN=""
fi
# Refuse to replace an unrelated app that happens to have the same name
if [[ -d "$APP" ]]; then
  existing="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP/Contents/Info.plist" 2>/dev/null || true)"
  [[ "$existing" == "$LABEL" ]] || die "$APP exists and is not SemSearch ($existing). Move it away or set SEMSEARCH_APP."
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating .venv…"
  if command -v uv >/dev/null; then
    uv venv -q -p 3.11 .venv
  else
    python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
      || die "Python 3.11+ is required (found $(python3 --version 2>&1)). Install uv or a newer Python."
    python3 -m venv .venv
  fi
fi
echo "Installing Python packages…"
if command -v uv >/dev/null; then
  uv pip install -q -p .venv/bin/python -r requirements.txt
else
  .venv/bin/pip install -q -r requirements.txt
fi

echo "Building the app…"
BUILD="$(mktemp -d)"
[[ -f mac/AppIcon.icns ]] || .venv/bin/python mac/make_icon.py mac/AppIcon
if [[ -z "$SWIFT_BIN" ]]; then
  SWIFT_BIN="$BUILD/bin"
  mac/build.sh "$SWIFT_BIN"
fi
for exe in SemSearch semsearch-ocr semsearch-fswatch; do
  [[ -x "$SWIFT_BIN/$exe" ]] || die "$SWIFT_BIN/$exe is missing."
done
# Helpers the Python service runs: OCR (Vision) and the new-file watcher (FSEvents)
mkdir -p bin "$BUILD/SemSearch.app/Contents/MacOS" "$BUILD/SemSearch.app/Contents/Resources"
cp "$SWIFT_BIN/semsearch-ocr" "$SWIFT_BIN/semsearch-fswatch" bin/
cp "$SWIFT_BIN/SemSearch" "$BUILD/SemSearch.app/Contents/MacOS/SemSearch"
cp mac/AppIcon.icns "$BUILD/SemSearch.app/Contents/Resources/AppIcon.icns"
cat > "$BUILD/SemSearch.app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>SemSearch</string>
  <key>CFBundleIdentifier</key><string>$LABEL</string>
  <key>CFBundleExecutable</key><string>SemSearch</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>SemSearchRepo</key><string>$REPO</string>
  <key>NSDocumentsFolderUsageDescription</key><string>Build a local search index. Nothing leaves this Mac.</string>
  <key>NSDesktopFolderUsageDescription</key><string>Build a local search index. Nothing leaves this Mac.</string>
  <key>NSDownloadsFolderUsageDescription</key><string>Build a local search index. Nothing leaves this Mac.</string>
  <key>NSFileProviderDomainUsageDescription</key><string>Index synced cloud files (downloaded files only).</string>
</dict>
</plist>
PLIST
if [[ -n "$SKIP_AGENT" ]]; then
  codesign --force --sign - "$BUILD/SemSearch.app"  # test mode: leave keychains alone
else
  mac/sign.sh "$BUILD/SemSearch.app"  # stable signature: folder permissions survive updates
fi

if [[ -z "$SKIP_AGENT" ]]; then
  # Stop the old version of *this* app (the search service is its child process)
  pkill -f "$APP/Contents/MacOS/SemSearch" 2>/dev/null || true
  sleep 2
  pkill -f "$REPO/.venv/bin/python -m semsearch.server" 2>/dev/null || true
fi
rm -rf "$APP"
mv "$BUILD/SemSearch.app" "$APP"
rm -rf "$BUILD"

if [[ -n "$SKIP_AGENT" ]]; then
  echo "Built $APP (test mode: no login item, no ss link)."
  exit 0
fi

AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/open</string><string>-g</string><string>$APP</string></array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
PLIST
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENT"

# `ss` command: only if the name is free (or already ours)
BIN="$(brew --prefix 2>/dev/null || echo /usr/local)/bin"
if [[ -d "$BIN" && -w "$BIN" ]]; then
  if [[ ! -e "$BIN/ss" && ! -L "$BIN/ss" ]] || [[ "$(readlink "$BIN/ss")" == "$REPO/ss" ]]; then
    ln -sf "$REPO/ss" "$BIN/ss"
  else
    echo "Note: $BIN/ss already exists, so the ss command was not linked. Use $REPO/ss instead."
  fi
fi

echo
echo "Installed $APP. Press ⌥Space to search (change it under Shortcut in the menu or the gear in the search box)."
echo "The first index build runs in the background (see ~/.semsearch/indexer.log)."
echo "macOS will ask SemSearch for access to Documents/Desktop/Downloads: allow it."
