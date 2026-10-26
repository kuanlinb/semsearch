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

Another app probably uses the same shortcut (Raycast, Alfred and ChatGPT often do), and macOS
does not tell SemSearch about the clash. Click the SemSearch icon in the menu bar, open
**Shortcut** and pick another one; it works right away. Or free ⌥Space in the other app.

Can't see the menu-bar icon? With many icons, macOS hides some of them behind the notch. Open
SemSearch again from the Applications folder or Spotlight: the search box appears, and the gear
on its right opens the same menu.

For a combination that is not in the menu, set `"hotkey"` in `~/.semsearch/config.json` (see
[Configuration](configuration.md)), e.g. `{ "hotkey": "control+option+cmd+k" }`, then quit
SemSearch from its menu and open it again.

## Uninstall

Installed with Homebrew: `semsearch-uninstall` (add `--all` to delete the index and model too), then
`brew uninstall semsearch`.

Installed from source, from the folder you cloned:

```bash
./uninstall.sh          # removes the app, its login item and the `ss` command
./uninstall.sh --all    # also deletes the index, logs and the downloaded model (about 2.3 GB)
cd .. && rm -rf semsearch   # the code and its Python environment
```

The plain version keeps the index and the model, so installing again later is quick.

## Development

```bash
uv pip install -p .venv/bin/python -r requirements-dev.txt   # or: .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests     # uses a tiny fake embedding model, no download
.venv/bin/python -m semsearch.indexer --quick
.venv/bin/python -m semsearch.server     # quit the menu-bar app first: it already runs one
```

Logs: `~/.semsearch/server.log`, `~/.semsearch/indexer.log`. If the service or the indexer
seems stuck, `kill -USR1 <pid>` writes every thread's stack trace to its log.
