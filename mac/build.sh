#!/bin/zsh
# Compile the three Swift programs: the menu-bar app and the helpers the Python service runs
# (OCR with Vision, the new-file watcher with FSEvents). Needs swiftc (xcode-select --install).
# Targets macOS 13 so the same binaries run on every supported system (release builds too).
# Usage: mac/build.sh OUTDIR    → OUTDIR/SemSearch, OUTDIR/semsearch-ocr, OUTDIR/semsearch-fswatch
set -euo pipefail
mkdir -p "$1"
OUT="$(cd "$1" && pwd)"
cd "$(dirname "$0")"
TARGET="arm64-apple-macos13.0"
swiftc -O -target "$TARGET" main.swift -o "$OUT/SemSearch"
swiftc -O -target "$TARGET" ocr.swift -o "$OUT/semsearch-ocr"
swiftc -O -target "$TARGET" fswatch.swift -o "$OUT/semsearch-fswatch"
