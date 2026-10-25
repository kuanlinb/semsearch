# Limitations, uninstall and development

[← Back to README](../README.md)

## Limitations

- Audio and video are found by name only. OCR reads only the first 5 pages of a scanned PDF,
  skips images where no line of text is detected (most photos) and files over 40 MB,
  and a large backlog of images takes several index runs (15 minutes each by default).
- Indexing speed is bound by the Mac GPU: on an M4, about 200 file names or 8 documents per second.
- The app is ad-hoc signed, not notarized: build it yourself with `install.sh`.
- Files inside the Trash are not indexed (macOS requires Full Disk Access for that).
- On macOS 13, iCloud Drive files that are not downloaded appear as hidden `.icloud`
  placeholders and are not indexed (macOS 14+ uses File Provider and works).
- The search service listens on `127.0.0.1` only and rejects requests addressed to any other
  host (DNS-rebinding protection), but other user accounts on the same Mac can query it.
- If another program already uses port 8799, set a different `port`.

## ⌥Space does nothing

Another app probably uses the same shortcut (Raycast, Alfred, ChatGPT and input-method switching
often do), and macOS does not tell SemSearch about the clash. Either free ⌥Space in that app, or
pick another shortcut with `"hotkey"` in `~/.semsearch/config.json` (see
[Configuration](configuration.md)), for example:

```json
{ "hotkey": "option+shift+space" }
```

Then quit SemSearch from its menu-bar icon and open it again. The menu-bar icon always works too.

## Uninstall

Run these from the folder you cloned (`cd semsearch`):

```bash
osascript -e 'quit app "SemSearch"'      # stops the app and its search service
launchctl bootout gui/$(id -u)/io.github.kuanlinb.semsearch 2>/dev/null
rm -rf /Applications/SemSearch.app ~/Library/LaunchAgents/io.github.kuanlinb.semsearch.plist
rm -rf ~/.semsearch                       # the index, logs and the opened-files log (opens.db)
rm -rf ~/.cache/huggingface/hub/models--BAAI--bge-m3   # the model (about 2.3 GB)
for d in /opt/homebrew/bin /usr/local/bin; do         # the `ss` command, only if it is ours
  [[ "$(readlink "$d/ss")" == "$PWD/ss" ]] && rm "$d/ss"
done
cd .. && rm -rf semsearch                 # the code and its Python environment
```

## Development

```bash
uv pip install -p .venv/bin/python -r requirements-dev.txt   # or: .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests     # uses a tiny fake embedding model, no download
.venv/bin/python -m semsearch.indexer --quick
.venv/bin/python -m semsearch.server     # quit the menu-bar app first: it already runs one
```

Logs: `~/.semsearch/server.log`, `~/.semsearch/indexer.log`. If the service or the indexer
seems stuck, `kill -USR1 <pid>` writes every thread's stack trace to its log.
