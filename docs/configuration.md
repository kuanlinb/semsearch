# Configuration

[← Back to README](../README.md)

Optional `~/.semsearch/config.json` (any subset of these keys):

```json
{
  "extra_roots": ["~/Notes", "~/Dropbox"],
  "names_only_roots": ["~/code"],
  "exclude_substrings": ["/private/", "secret"],
  "reranker": "BAAI/bge-reranker-v2-m3"
}
```

| Key | Default | Meaning |
|---|---|---|
| `roots` | Documents, Desktop, Downloads, File Provider drives, iCloud Drive, Applications folders | Folders to index. Setting it **replaces** the default list. |
| `extra_roots` | `[]` | Added to `roots`; the easy way to add a folder. |
| `hot_roots` | Downloads, Desktop | Rescanned every 30 min. Must also be in `roots`. |
| `names_only_roots` | `[]` | Index file names only, never read contents. |
| `exclude_substrings` | `[]` | Skip files and folders whose full path contains any of these. |
| `model` | `BAAI/bge-m3` | Embedding model. **Changing it rebuilds the whole index.** |
| `embed_backend` | `"onnx"` | `"onnx"`: bge-m3 quantized to int8 on ONNX Runtime, no PyTorch needed (smaller install, starts faster, indexes about 3× slower). `"torch"`: PyTorch on the Apple GPU; run `install.sh` again to add PyTorch. Indexes built before 0.1.3 keep `"torch"`. **Changing it rebuilds the whole index.** |
| `onnx_model` | (download) | A local folder with `model.onnx`, `model.onnx_data` and `tokenizer.json` to use instead of the download. |
| `reranker` | `""` (off) | Cross-encoder model id, e.g. `BAAI/bge-reranker-v2-m3` (2.2 GB download; needs PyTorch, which `install.sh` then adds). Slow on a laptop: about 8 s per search on an M4 with the defaults. With a reranker, weaker results are dimmed and unrelated ones hidden; the cut-offs are calibrated for this model. |
| `rerank_top` | `40` | How many results the reranker re-scores. Below 40, the results after them, up to the 40th, are shown dimmed instead of hidden. |
| `remote_reranker` | `""` (off) | URL of a [remote reranker](../remote/README.md), e.g. `http://127.0.0.1:8798`. Used before the local `reranker`; falls back to it, or to the fast order, when unreachable. |
| `remote_reranker_ssh` | `""` | SSH host (e.g. `my-gpu-box`) the service keeps a tunnel to for `remote_reranker`'s port. |
| `ocr_minutes` | `15` | Minutes per index run spent on OCR; the rest continues next run. `0` turns OCR off. |
| `port` | `8799` | Local port of the search service (or set `SEMSEARCH_PORT`). |
| `hotkey` | `"option+space"` | Shortcut that opens the search box. Easiest to change from the menu-bar icon (**Shortcut**); here any combination works, e.g. `"option+shift+space"` or `"cmd+shift+k"`: `cmd`, `option`, `control`, `shift` plus `space`, a letter or a digit. Takes effect when the app restarts. |

Invalid JSON in the config file is ignored (defaults are used). Package folders
(`node_modules`, `.venv`, `.git`, build output…) are always skipped, and a folder of hundreds of
machine-named files (a dataset) is indexed as one entry. Legacy, non-File-Provider sync folders
such as `~/Dropbox` are not added automatically: put them in `extra_roots`.
