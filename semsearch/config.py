"""Settings: which folders to scan, what to skip, which model to use, where data lives.

Override any key of DEFAULTS in ~/.semsearch/config.json, e.g.
    {"roots": ["~/Documents", "~/Notes"], "names_only_roots": ["~/code"]}
"""
import json
import os
from pathlib import Path

HOME = Path.home()
DATA_DIR = Path(os.environ.get("SEMSEARCH_DATA", HOME / ".semsearch"))
DB_PATH = DATA_DIR / "index.db"
USER_CONFIG = DATA_DIR / "config.json"
# Models downloaded by SemSearch itself (the ONNX runtime); PyTorch models use the Hugging Face cache
MODELS_DIR = Path(os.environ.get("SEMSEARCH_MODELS", HOME / ".semsearch" / "models"))


def cloud_drives():
    """Synced cloud folders: OneDrive, Google Drive, Dropbox (File Provider) and iCloud Drive."""
    out = []
    cs = HOME / "Library/CloudStorage"
    if cs.is_dir():
        out += sorted(str(p) for p in cs.iterdir() if p.is_dir() and not p.name.startswith("."))
    icloud = HOME / "Library/Mobile Documents/com~apple~CloudDocs"
    if icloud.is_dir():
        out.append(str(icloud))
    return out


DEFAULTS = {
    "roots": [
        str(HOME / "Documents"),
        str(HOME / "Desktop"),
        str(HOME / "Downloads"),
        *cloud_drives(),
        # Apps are indexed by name only (including their localized names)
        "/Applications",
        "/System/Applications",
        str(HOME / "Applications"),
    ],
    # Added to "roots" (setting "roots" itself replaces the default list)
    "extra_roots": [],
    # Rescanned every 30 minutes; everything else at least every 6 hours
    "hot_roots": [str(HOME / "Downloads"), str(HOME / "Desktop")],
    # Index file names only, never read contents (e.g. code projects whose Markdown
    # notes would crowd out the documents you are actually looking for)
    "names_only_roots": [],
    # Skip any file or folder whose full path contains one of these strings
    "exclude_substrings": [],
    "port": 8799,
    "model": "BAAI/bge-m3",
    # "torch" (PyTorch, Apple GPU) or "onnx" (ONNX Runtime int8 on the CPU, no PyTorch needed)
    "embed_backend": "torch",
    # Optional second-stage cross-encoder; "" disables it (slow on laptops)
    "reranker": "",
    "rerank_top": 40,
    # Optional reranker on another machine (see remote/README.md): its URL, and an SSH host
    # the search service keeps a tunnel to, e.g.
    #   "remote_reranker": "http://127.0.0.1:8798", "remote_reranker_ssh": "my-gpu-box"
    "remote_reranker": "",
    "remote_reranker_ssh": "",
    # Minutes per index run spent on OCR (images, scanned PDFs); the rest waits for the
    # next run. 0 turns OCR off.
    "ocr_minutes": 15,
}

# Directory names skipped entirely (packages, caches, VCS, build output)
EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", ".env",
    "__pycache__", "site-packages", "dist-packages", ".cache", "build", "dist",
    ".next", ".nuxt", ".idea", ".vscode", "DerivedData", "Pods", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "target", ".gradle",
    "vendor", "bower_components", ".ipynb_checkpoints", ".npm", ".yarn",
    ".conda", "miniconda3", "anaconda3", ".Trash", "Library", "wandb",
    "mlruns", "lightning_logs", ".terraform", "coverage", ".pnpm-store",
}
# Package directories treated as a single file
BUNDLE_EXT = {".app", ".bundle", ".framework", ".photoslibrary", ".pages",
              ".key", ".numbers", ".textbundle", ".xcodeproj", ".xcworkspace",
              ".rtfd", ".musiclibrary", ".logicx", ".fcpbundle"}

# A folder with this many files of one extension, mostly with machine-generated
# names (IMG_0001.jpg, frame_000123.png), is treated as a dataset: only the folder
# itself is indexed. Document types are always indexed one by one.
DATASET_THRESHOLD = 150
DATASET_SERIAL_RATIO = 0.6
NEVER_COLLAPSE_EXT = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
                      ".key", ".pages", ".numbers", ".md", ".ipynb", ".tex", ".rtf",
                      ".odt", ".epub", ".zip", ".dmg", ".app"}

DOC_EXT = {".pdf", ".docx", ".pptx", ".xlsx", ".ipynb", ".doc", ".rtf", ".odt"}
# Only "documents" are read; code, saved web pages, csv/json/log are indexed by
# name only because their contents are mostly noise for this kind of search.
PROSE_EXT = {".txt", ".md", ".markdown", ".tex", ".rst", ".org", ".srt", ".vtt"}
CONTENT_EXT = PROSE_EXT | DOC_EXT
MAX_TEXT_BYTES = 2_000_000      # plain text: read only the beginning
MAX_DOC_BYTES = 80_000_000      # larger documents: name only
MAX_CHARS_PER_FILE = 40_000
CHUNK_CHARS = 450
CHUNK_OVERLAP = 80
MAX_CHUNKS_PER_FILE = int(os.environ.get("SEMSEARCH_MAX_CHUNKS", 30))


def embed_backend():
    """"torch" or "onnx"; SEMSEARCH_EMBED_BACKEND overrides the config file."""
    return os.environ.get("SEMSEARCH_EMBED_BACKEND") or load().get("embed_backend", "torch")


def device():
    """Apple GPU when there is one; SEMSEARCH_DEVICE=cpu forces the CPU (CI runners have no usable GPU)."""
    forced = os.environ.get("SEMSEARCH_DEVICE")
    if forced:
        return forced
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"

# OCR: text in images and scanned PDFs is recognized with macOS Vision (bin/semsearch-ocr)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".heic", ".tiff", ".tif", ".bmp", ".gif", ".webp"}
OCR_MAX_BYTES = 40_000_000

FULL_EVERY = 6 * 60 * 60  # a --quick run upgrades itself to a full scan after this long

# macOS File Provider "cloud-only" flag: reading contents would trigger a download,
# so such files are indexed by name only.
SF_DATALESS = 0x40000000


L10N_DIR = Path(__file__).resolve().parent.parent / "l10n"


def ui_language():
    """The first preferred macOS language, as named in l10n/ ("zh-Hant", "ja", ...); "en" if unknown."""
    import subprocess
    try:
        out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True,
                             text=True, timeout=5).stdout
        langs = [x.strip(' ",') for x in out.splitlines() if x.strip(' ",()')]
    except Exception:
        langs = []
    parts = (langs[0] if langs else "en").split("-")
    if parts[0] != "zh":
        return parts[0]
    return "zh-Hant" if "Hant" in parts or parts[-1] in ("TW", "HK", "MO") else "zh-Hans"


def translations(lang):
    """English text -> text in `lang`, from l10n/<lang>.json ({} when there is no file)."""
    try:
        return json.loads((L10N_DIR / f"{lang}.json").read_text())
    except Exception:
        return {}


def load():
    cfg = dict(DEFAULTS)
    if USER_CONFIG.exists():
        try:
            cfg.update(json.loads(USER_CONFIG.read_text()))
        except Exception:
            pass
    cfg["roots"] = list(cfg["roots"]) + list(cfg.get("extra_roots", []))
    for key in ("roots", "hot_roots", "names_only_roots"):
        cfg[key] = [os.path.normpath(os.path.expanduser(r)) for r in cfg[key]]
    if os.environ.get("SEMSEARCH_PORT"):
        cfg["port"] = int(os.environ["SEMSEARCH_PORT"])
    return cfg
