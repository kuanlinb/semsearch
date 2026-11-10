#!/bin/zsh
# Remove SemSearch: the app, its login item and the `ss` command.
# Usage: ./uninstall.sh          keeps the index and the downloaded model, so a reinstall is quick
#        ./uninstall.sh --all    also deletes the index, logs and the model (about 600 MB)
# This folder itself (the code and its .venv) is left for you to delete.
# Testing: SEMSEARCH_APP=/tmp/SemSearch.app SEMSEARCH_SKIP_AGENT=1 ./uninstall.sh
#          removes only that app; does not touch running apps, login items or the `ss` link
set -euo pipefail
cd "$(dirname "$0")"
REPO="$PWD"
APP="${SEMSEARCH_APP:-/Applications/SemSearch.app}"
SKIP_AGENT="${SEMSEARCH_SKIP_AGENT:-}"
LABEL="io.github.kuanlinb.semsearch"
ALL=""
case "${1:-}" in
  "") ;;
  --all) ALL=1 ;;
  *) echo "Usage: ./uninstall.sh [--all]" >&2; exit 2 ;;
esac

if [[ -z "$SKIP_AGENT" ]]; then
  # Quitting the app also stops its search service and any indexing run
  osascript -e "tell application id \"$LABEL\" to quit" 2>/dev/null || true
  sleep 2
  pkill -f "$APP/Contents/MacOS/SemSearch" 2>/dev/null || true
  pkill -f "$REPO/.venv/bin/python -m semsearch" 2>/dev/null || true
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
  # The `ss` command, only where it points to this folder
  for bin in /opt/homebrew/bin /usr/local/bin; do
    if [[ -L "$bin/ss" && "$(readlink "$bin/ss")" == "$REPO/ss" ]]; then
      rm -f "$bin/ss"
    fi
  done
fi

# Only an app that really is SemSearch
if [[ -d "$APP" ]]; then
  existing="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP/Contents/Info.plist" 2>/dev/null || true)"
  if [[ "$existing" == "$LABEL" ]]; then
    rm -rf "$APP"
  else
    echo "Left $APP alone: it is not SemSearch ($existing)."
  fi
fi

# Set by the Homebrew wrapper (semsearch-uninstall)
if [[ -n "${SEMSEARCH_BREW:-}" ]]; then
  again="semsearch-uninstall --all"; code="brew uninstall semsearch"
else
  again="./uninstall.sh --all"; code="cd .. && rm -rf \"$REPO\""
fi
if [[ -n "$ALL" ]]; then
  rm -rf "${SEMSEARCH_DATA:-$HOME/.semsearch}"
  if [[ -z "$SKIP_AGENT" ]]; then  # the signing certificate made by install.sh
    security delete-keychain "$HOME/Library/Keychains/semsearch-signing.keychain-db" 2>/dev/null || true
    rm -f "$HOME/Library/Application Support/SemSearch/signing-keychain.pw"
    rmdir "$HOME/Library/Application Support/SemSearch" 2>/dev/null || true
  fi
  # Homebrew keeps the Python environment outside the package so it survives upgrades
  if [[ -L .venv ]]; then
    venv="$(readlink .venv)"
    [[ "$venv" == */var/semsearch/venv ]] && rm -rf -- "$venv"
  fi
  echo "Removed SemSearch, its index and the model."
  # The PyTorch backend's model sits in the Hugging Face cache, which other programs share:
  # left alone, never deleted for them
  hf="${HF_HOME:-$HOME/.cache/huggingface}/hub"
  if [[ -d "$hf/models--BAAI--bge-m3" || -d "$hf/models--BAAI--bge-reranker-v2-m3" ]]; then
    echo "Note: the PyTorch models in $hf (models--BAAI--bge-m3, models--BAAI--bge-reranker-v2-m3)"
    echo "      are shared with other programs and were kept; delete them yourself if nothing else uses them."
  fi
else
  echo "Removed SemSearch. The index (~/.semsearch) and the model are kept; $again deletes them."
fi
echo "To delete the code too: $code"
