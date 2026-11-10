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
# hw.optional.arm64, not uname: a Terminal running under Rosetta reports x86_64 on an M-series Mac
[[ "$(sysctl -n hw.optional.arm64 2>/dev/null)" == "1" ]] || die "SemSearch needs an Apple silicon Mac (M1 or newer)."
[[ "$(uname -m)" == "arm64" ]] || die "This Terminal runs under Rosetta (Intel mode). Open a normal Terminal window and run this again."
# onnxruntime and PyTorch ship for macOS 14 and later only
(( ${$(sw_vers -productVersion)%%.*} >= 14 )) || die "SemSearch needs macOS 14 (Sonoma) or later; this Mac has $(sw_vers -productVersion)."
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

# Python 3.11-3.14: the versions every pinned package has wheels for (3.15 has none yet)
supported() { "$1" -c 'import sys; sys.exit(not (3, 11) <= sys.version_info[:2] <= (3, 14))' 2>/dev/null; }
REBUILD=""
if [[ -e .venv/bin/python ]] && ! supported .venv/bin/python; then
  echo "Rebuilding .venv: it uses $(.venv/bin/python --version 2>&1), which SemSearch does not support."
  REBUILD=1
fi
if [[ -n "$REBUILD" || ! -x .venv/bin/python ]]; then
  echo "Creating .venv…"
  # Under Homebrew .venv is a link to a folder outside the versioned package (it survives
  # upgrades). venv refuses to create an environment through a link, so it is made at the target.
  VENV=.venv
  if [[ -L .venv ]]; then
    VENV="$(readlink .venv)"
    mkdir -p "$(dirname "$VENV")"
  fi
  PY=""
  for c in python3 python3.13 python3.12 python3.11 python3.14; do  # python3 first: the Homebrew wrapper puts python@3.12 there
    if command -v "$c" >/dev/null && supported "$(command -v "$c")"; then PY="$(command -v "$c")"; break; fi
  done
  if [[ -n "$PY" ]]; then
    "$PY" -m venv --clear "$VENV"  # --clear empties an old or broken environment in place
  elif command -v uv >/dev/null; then
    # Newer uv refuses to replace an environment unless asked; older uv has no --clear flag
    UV_VENV_CLEAR=1 uv venv -q -p 3.12 "$VENV"
  else
    die "Python 3.11 to 3.14 is needed (python3 here is $(python3 --version 2>&1)). Install one with: brew install python@3.13"
  fi
fi
# PyTorch only when the config asks for it ("embed_backend": "torch", or a reranker on this Mac).
# An index built before the ONNX backend stays on PyTorch, so an update does not rebuild it.
REQS="$(.venv/bin/python - "${SEMSEARCH_DATA:-$HOME/.semsearch}" <<'PY'
import json, os, sqlite3, sys
data = sys.argv[1]
path = os.path.join(data, "config.json")
readable = True
try:
    cfg = json.load(open(path)) if os.path.exists(path) else {}
except ValueError:
    print(f"Note: {path} is not valid JSON; fix it, SemSearch does not index until then.", file=sys.stderr)
    cfg, readable = {}, False
if not isinstance(cfg, dict):
    cfg, readable = {}, False
if "embed_backend" not in cfg and os.path.exists(os.path.join(data, "index.db")):
    try:
        db = sqlite3.connect(os.path.join(data, "index.db"))
        meta = dict(db.execute("SELECT k, v FROM meta WHERE k IN ('model', 'backend')"))
    except sqlite3.Error:
        meta = {}
    if "model" in meta and "backend" not in meta:
        cfg["embed_backend"] = "torch"
        if readable:  # never overwrite settings we could not read
            json.dump(cfg, open(path, "w"), indent=2)
        print('Keeping PyTorch for your index ("embed_backend": "onnx" in the config switches).', file=sys.stderr)
print("requirements.txt" if cfg.get("embed_backend") == "torch" or cfg.get("reranker") else "requirements-onnx.txt")
PY
)"
echo "Installing Python packages ($REQS)…"
if command -v uv >/dev/null; then
  uv pip install -q -p .venv/bin/python -r "$REQS"
else
  .venv/bin/pip install -q -r "$REQS"
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
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSUIElement</key><true/>
  <key>SemSearchRepo</key><string></string>
  <key>NSDocumentsFolderUsageDescription</key><string>Build a local search index. Nothing leaves this Mac.</string>
  <key>NSDesktopFolderUsageDescription</key><string>Build a local search index. Nothing leaves this Mac.</string>
  <key>NSDownloadsFolderUsageDescription</key><string>Build a local search index. Nothing leaves this Mac.</string>
  <key>NSFileProviderDomainUsageDescription</key><string>Index synced cloud files (downloaded files only).</string>
</dict>
</plist>
PLIST
# plutil escapes the path (a folder like ~/R&D would otherwise break the XML)
plutil -replace SemSearchRepo -string "$REPO" "$BUILD/SemSearch.app/Contents/Info.plist"
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
mkdir -p "$HOME/Library/LaunchAgents"  # a new user account does not have it yet
cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/open</string><string>-g</string><string>$APP</string></array>
  <key>RunAtLoad</key><true/>
  <key>AssociatedBundleIdentifiers</key><string>$LABEL</string>
</dict>
</plist>
PLIST
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
# Fails when background items are turned off in System Settings; the app still starts now
launchctl bootstrap "gui/$(id -u)" "$AGENT" 2>/dev/null \
  || echo "Note: SemSearch could not be added to the login items (System Settings › General › Login Items › Allow in the Background)."
open -g "$APP"

# `ss` command: only if the name is free (or already ours)
BIN="$(brew --prefix 2>/dev/null || echo /usr/local)/bin"
if [[ -d "$BIN" && -w "$BIN" ]]; then
  if [[ ! -e "$BIN/ss" && ! -L "$BIN/ss" ]] || [[ "$(readlink "$BIN/ss")" == "$REPO/ss" ]]; then
    ln -sf "$REPO/ss" "$BIN/ss"
  else
    echo "Note: $BIN/ss already exists, so the ss command was not linked. Use $REPO/ss instead."
  fi
else
  echo "Note: the ss command was not linked ($BIN is missing or not writable). Use $REPO/ss instead."
fi

echo
echo "Installed $APP. Press ⌥Space to search (change it under Shortcut in the menu or the gear in the search box)."
echo "The first index build runs in the background (see ~/.semsearch/indexer.log)."
echo "macOS will ask SemSearch for access to Documents/Desktop/Downloads: allow it."
