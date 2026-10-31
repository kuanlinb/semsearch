# Changelog

## Unreleased

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

- Homebrew installs no longer need the Xcode Command Line Tools on macOS 14 or later: the app
  comes already compiled.
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
