# Changelog

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
