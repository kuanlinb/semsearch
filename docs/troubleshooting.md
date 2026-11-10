# Limitations, uninstall and development

[← Back to README](../README.md)

## Limitations

- Audio and video are found by name only. OCR reads only the first 5 pages of a scanned PDF,
  skips images where no line of text is detected (most photos) and files over 40 MB,
  and a large backlog of images takes several index runs (15 minutes each by default).
- Indexing speed is bound by the Mac GPU: on an M4, about 200 file names or 8 documents per second.
- The app is not notarized: `install.sh` builds it on your Mac (Homebrew ships it already compiled)
  and signs it with a self-signed certificate made on your Mac and kept in its own keychain
  (`semsearch-signing`), so macOS keeps your folder permissions across updates. `./uninstall.sh --all` removes that keychain too.
- Files inside the Trash are not indexed (macOS requires Full Disk Access for that).
- The search service listens on `127.0.0.1` only and rejects requests addressed to any other
  host (DNS-rebinding protection), but other user accounts on the same Mac can query it while
  it runs. The index files themselves (`~/.semsearch`) are readable by your account only.
- If another program already uses port 8799, set a different `port`. Each account on the Mac has its own
  default port, and the app never uses another account's service.

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

## Use ⌘Space instead of Spotlight

⌘Space is the easiest shortcut to reach, but Spotlight owns it. To give it to SemSearch:

1. System Settings › Keyboard › Keyboard Shortcuts › Spotlight: turn off **Show Spotlight search**.
2. In SemSearch's menu (menu-bar icon or the gear in the search box), pick **Shortcut › ⌘ Space**.

Spotlight still opens with the 🔍 key (F4) on Mac keyboards that have it.

## Uninstall

Installed with Homebrew: `semsearch-uninstall` (add `--all` to delete the index and model too), then
`brew uninstall semsearch`.

Installed from source, from the folder you cloned:

```bash
./uninstall.sh          # removes the app, its login item and the `ss` command
./uninstall.sh --all    # also deletes the index, logs and the downloaded model (about 600 MB)
cd .. && rm -rf semsearch   # the code and its Python environment
```

The plain version keeps the index and the model, so installing again later is quick.

### Removing what is left

Ran `brew uninstall semsearch` (or deleted the cloned folder) before the uninstall step? The app
then says its files are missing. Remove the rest by hand:

```bash
osascript -e 'tell application id "io.github.kuanlinb.semsearch" to quit'
launchctl bootout gui/$(id -u)/io.github.kuanlinb.semsearch
rm -f ~/Library/LaunchAgents/io.github.kuanlinb.semsearch.plist
rm -rf /Applications/SemSearch.app
security delete-keychain ~/Library/Keychains/semsearch-signing.keychain-db
rm -rf ~/Library/Application\ Support/SemSearch            # the signing keychain's password
rm -rf ~/.semsearch                                   # the index, settings and model
rm -rf "$(brew --prefix)/var/semsearch"               # Homebrew only: its Python environment
ss="$(brew --prefix)/bin/ss"; [ -L "$ss" ] && [ ! -e "$ss" ] && rm "$ss"   # only a broken link
```

## The search service does not start

The menu says what went wrong when it can. `~/.semsearch/server.log` has the details.

- **"The SemSearch program files are missing"**: the folder the app runs from was moved or deleted, or
  `brew upgrade` replaced it. Run `semsearch-install` (Homebrew) or `./install.sh` again.
- **Downloading the language model** stays at the same percentage: the download resumes where
  it stopped once the network is back; nothing needs to be deleted.
- **config.json has a problem**: the menu names the setting. Until it is fixed, SemSearch keeps
  searching the existing index but does not update it, so a typo never removes files from it.

## Development

```bash
uv pip install -p .venv/bin/python -r requirements-dev.txt   # or: .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests     # uses a tiny fake embedding model, no download
.venv/bin/python -m semsearch.indexer --quick
.venv/bin/python -m semsearch.server     # quit the menu-bar app first: it already runs one
```

Logs: `~/.semsearch/server.log`, `~/.semsearch/indexer.log`. If the service or the indexer
seems stuck, `kill -USR1 <pid>` writes every thread's stack trace to its log.
