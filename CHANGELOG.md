# Changelog

## 0.1.7 (2026-11-10)

The less common problems found in the same review as 0.1.6.

- **A query that is a file's name puts that file first** ("履歷" → 履歷.txt, "report" →
  report.pdf). Short files with no text of their own used to lose to long documents that only
  mention the word.
- **Names stored decomposed are found**: macOS often stores Korean, Japanese kana with
  dakuten and accented names as NFD, while typed text is NFC, so "데이터", "データ" or "résumé"
  missed by name.
- **Narrowing the scope cleans up**: a folder taken out of `roots` (or a cloud drive that was
  removed) leaves the index after a full scan an hour later, and folders added to
  `names_only_roots` lose their document text. If most of the index would go (a mistyped
  `roots`), nothing is removed; an empty `roots` is reported as a config problem.
- **The service no longer crashes when tens of thousands of folders change at once**
  (unpacking a big archive): the changed folders go to the indexer through a file, and one bad
  round of the service's loop is logged instead of ending it.
- **A run that changed nothing no longer makes the service reload the whole index** (this
  happened every 30 minutes, doubling memory while it reloaded).
- **OCR and image search re-check that a file is still on the Mac** before reading it, so a
  file evicted to iCloud or OneDrive since the scan is not downloaded. OCR text can no longer
  end up on the wrong file (a name with a line break shifted every answer), names ending in a
  space are read, and images claiming a huge size are skipped instead of decoded.
- **Image search stops when llama-server stops answering** instead of marking every remaining
  image as empty, which was never retried; an image the server refuses is skipped alone.
- **Each account on a Mac gets its own port** (8799, 8800, …) and the app refuses a service
  that belongs to another account instead of showing that account's files.
- **Searches sent by other web sites are refused**, so a page you visit cannot make your
  browser run searches on this Mac.
- One-letter queries no longer walk every file name, and the panel opens on the display the
  pointer is on.
- The signing keychain's password moved to `~/Library/Application Support/SemSearch`, so
  deleting `~/.semsearch` to start over no longer makes macOS ask for folder access again; an
  interrupted install no longer leaves the signing keychain on the keychain search list.
- An app with an unusual `Info.plist` no longer stops every index run.

## 0.1.6 (2026-11-10)

Fixes found by trying SemSearch the way a new user would, on a fresh install.

- **A mistake in `config.json` can no longer empty the index.** A string where a list belongs
  (`"exclude_substrings": "secret"`) used to exclude every path containing one of its letters,
  and the next run deleted everything. Now a single string is read as a one-item list, settings
  of the wrong type (or `null`, or an unknown `embed_backend`) are ignored, and while the file is invalid JSON or has such a problem the
  index is not updated at all (search keeps working); the menu names the problem.
- **A scan that suddenly misses most files removes nothing at once** (a drive or cloud folder
  that did not answer, a setting that excluded too much): each missing entry is removed only if a
  scan at least an hour later still misses it, and entries found again are kept.
- **Folders of screenshots are indexed again.** 150 or more screenshots in one folder were taken
  for a machine-made dataset and skipped, OCR text and all, along with any file you had named
  yourself there. Screenshot names no longer count as machine-made, Desktop and Downloads are
  never folded, and inside a real dataset only the machine-named files are left out.
- **A query of only a file type works**: "screenshot", "截圖", "pdf", "folder" list the newest
  files of that type instead of nothing.
- **Fewer false time and source filters**: "notes on edge detection" is no longer "from Edge",
  "lecture on line integrals" not "from LINE", "hard drive files" not "from Google Drive".
  "latest" / "最新" ranks the newest version first instead of hiding files older than 30 days.
  "過去二十五天" means 25 days (it meant 2).
- **The model download resumes** where it stopped (it is about 590 MB), times out instead of
  hanging, retries, works with a python.org Python that has no certificates installed, and shows
  its progress in the menu and the search box.
- **The app says why search is not working** instead of "may still be starting" forever: its
  files are missing (moved, or `brew upgrade` without `semsearch-install`), the model is
  downloading, `config.json` has a problem, or the service keeps stopping. A service that cannot
  start is retried less and less often (up to every 10 minutes) instead of every 10 seconds, and
  `server.log` no longer grows without end.
- **A shortcut taken by another app is reported** in the menu and the search box (⌥Space is
  also used by Raycast, Alfred and others).
- **The index is private to your account**: `~/.semsearch` was readable by other accounts on
  the Mac, though it holds the text of your documents.
- Install: macOS 14 or later is now required (onnxruntime and PyTorch no longer support 13; the
  README said 13). The installer picks Python 3.11 to 3.14 and rebuilds an environment made with
  an unsupported one (`brew install python` now gives 3.15, which nothing supports yet). It
  creates `~/Library/LaunchAgents` on a new account, starts the app even when login items are
  turned off, works in a folder whose path has `&`, reports when the `ss` command was not
  linked, and detects Rosetta Terminals.
- Homebrew: the Python environment now lives in `$(brew --prefix)/var/semsearch` so it survives
  `brew upgrade`, and the OCR and file-watcher helpers are installed with the package.
- `uninstall.sh --all` no longer deletes the PyTorch models in the shared Hugging Face cache; it
  says where they are. The docs list what to remove by hand after a `brew uninstall` alone, and
  give the model size as 600 MB (not 2.3 GB).

## 0.1.5 (2026-11-09)

- Fixed: running once with a different backend (`SEMSEARCH_EMBED_BACKEND`) no longer wipes the
  index. Only `"embed_backend"` in `config.json` (or `--full`) rebuilds it; a one-off run with
  another backend logs why and leaves the index alone.
- New: memory limits. The search service restarts itself past `max_server_mb` (default 5000,
  at most once an hour), the indexer stops past `max_indexer_mb` (default 4000) and the next run
  continues, so a runaway process can't slow the whole Mac down.
- For maintainers: `tools/memcheck.py` measures memory with the real model and index, on a clone
  of the data folder, and fails when a budget is exceeded; a new test catches reloads that keep
  old vectors alive.

## 0.1.4 (2026-11-09)

- Uses less memory. With the PyTorch backend the search server drops from about 6.3 GB to
  3.3 GB and no longer grows each time the index reloads: bge-m3 is converted once to a float16
  safetensors copy in `~/.semsearch/models/` (the float32 original left a 1.1 GB CPU copy behind
  after moving to the GPU), cached GPU memory is returned after each reload and during indexing,
  and reloads read the vectors in batches instead of all at once. The default ONNX backend
  starts at 1.3 GB instead of 1.9 GB. Search results are unchanged.

## 0.1.3 (2026-10-31)

- Spotlight-style touches on the panel: a type filter under the search box (⌘1–⌘6: all,
  documents, PDFs, slides and sheets, images, folders), a progress bar while the index is first
  being built, ↑ in an empty box for earlier searches (kept on your Mac; the menu can clear
  them), and "Search in Finder" (⌘F) for when the file isn't there.
- Time and source words become filters: “the quote Amy sent on LINE last week” searches
  “quote” among last week's files that came from LINE. A chip in the search box shows the
  conditions and its ✕ searches without them. On a 48-question test the right file came first
  for 42 questions instead of 24. `"conditions": false` turns it off.
- Each result highlights the sentence that answers the question, in any language (a Chinese
  question highlights the answer in an English contract), with the query words in bold and the
  page number for PDFs. It is added to the search that runs after typing pauses: about 0.3 s
  on an M4.
- The result list is quieter: long folder paths keep their start and last two folders, the
  "in folder" count shows on the selected row, and the footer says how many results.
- Optional: a local int8 reranker (`"onnx_reranker"`, see `eval/local_rerank/`) re-scores
  the top 5 in about 0.3 s without PyTorch.
- No PyTorch by default: bge-m3 runs quantized to int8 on ONNX Runtime. The install is about 170 MB
  of Python packages instead of 1 GB and the model 590 MB instead of 2.2 GB; search quality is the
  same, the service starts in about a second, but the first index build is about 3× slower.
  Existing installs keep PyTorch and their index; `"embed_backend": "onnx"` switches.
- A reranker on this Mac still needs PyTorch: `install.sh` adds it when the config has one.
- Every indexed folder updates on its own: new, edited, moved and deleted files show up in about
  a minute, not only in Downloads and Desktop (other folders used to wait for the 6-hour scan).
  Only the folders that changed are rescanned.
- The first searches after login or wake no longer wait on a remote reranker that is not
  reachable yet: it is used once a background check sees it answer.
- The menu no longer has "Open Web Version".

## 0.1.2 (2026-10-26)

- The Homebrew formula compiles the app itself, so a bottle carries it ready to run. Bottles
  shipped with 0.1.3 and cover macOS 15 and later; there, installs need no Xcode Command Line
  Tools. (This entry first said macOS 14: Homebrew has no Python bottles for macOS 14, so it
  builds from source and still needs them.)
- `install.sh` explains how to get the Command Line Tools when they are missing or only a stub.
- Searching for a number or a code (an invoice or booking number, an amount, a plate) finds the
  file that contains it: on a 249-file test set those lookups went from rank 13-20 to first.
- With a reranker, results come in two tiers: close matches as usual, less related ones dimmed,
  unrelated ones hidden. The list animates when the reranked order arrives.
- Search box: the usual Edit shortcuts work, Command-C copies the file, Esc clears the text first,
  results can be dragged out, and a right-click menu.
- A settings gear in the search box; opening the app again shows the search box.
- The first launch opens the search box with the shortcut in its hint.
- Folder permissions survive updates: the app is signed with the same local certificate each time.
- Folders that were not yet allowed are checked again every 30 seconds.
- Optional: `"embed_backend": "onnx"` runs the embedding model without PyTorch (smaller install,
  slower indexing). PyTorch stays the default.
- `eval/lookalike/`: a reproducible test set of 249 fictional files with look-alikes and 76 questions.

## 0.1.1 (2026-10-26)

- Install with Homebrew: `brew install kuanlinb/tap/semsearch && semsearch-install`.
- The search box no longer shows a square edge around its rounded corners.

## 0.1.0 (2026-10-26)

First public release.

- Search files and apps on your Mac by describing them, in any language (bge-m3, runs locally).
- Reads PDF, Word, PowerPoint, Excel, Markdown, plain text and notebooks; OCR for screenshots
  and scanned PDFs.
- Finds apps by what they do, and common places such as the Trash and Downloads.
- ⌥Space search panel with Liquid Glass on macOS 26; the shortcut can be changed from the
  menu-bar menu.
- Interface in English, Traditional Chinese, Simplified Chinese, Japanese and Korean.
- New files in Downloads and Desktop are searchable in about 30 seconds.
- Optional reranker on another machine with a GPU.
- `install.sh` and `uninstall.sh`.
