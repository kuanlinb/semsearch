# Limitations, uninstall and development

[← Back to README](../README.md)

## Limitations

- Audio and video are found by name only. OCR reads only the first 5 pages of a scanned PDF,
  skips images where no line of text is detected (most photos) and files over 40 MB,
  and a large backlog of images takes several index runs (15 minutes each by default).
- Indexing speed is bound by the Mac GPU (~10 chunks/s for bge-m3 on an M4).
- The app is ad-hoc signed, not notarized: build it yourself with `install.sh`.
- Files inside the Trash are not indexed (macOS requires Full Disk Access for that).
- On macOS 13, iCloud Drive files that are not downloaded appear as hidden `.icloud`
  placeholders and are not indexed (macOS 14+ uses File Provider and works).
- The search service listens on `127.0.0.1` only and rejects requests addressed to any other
  host (DNS-rebinding protection), but other user accounts on the same Mac can query it.
- If another program already uses port 8799, set a different `port`.

## Uninstall

```bash
launchctl bootout gui/$(id -u)/io.github.kuanlinb.semsearch
rm -rf /Applications/SemSearch.app ~/Library/LaunchAgents/io.github.kuanlinb.semsearch.plist
rm -rf ~/.semsearch                       # the index, logs and the opened-files log (opens.db)
rm -f "$(brew --prefix)/bin/ss"           # if it points to this repo
rm -rf ~/.cache/huggingface/hub/models--BAAI--bge-m3   # the model
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
