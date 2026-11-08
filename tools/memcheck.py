"""Release gate for memory: run before every release, on a Mac with a real index.

CI has no GPU and only a tiny index, so it cannot see how much memory the real model and a
large index take, or whether the server grows over hours. This script measures that in fresh
processes and fails when a budget is exceeded:

  .venv/bin/python tools/memcheck.py            # the backend from your config
  SEMSEARCH_EMBED_BACKEND=torch .venv/bin/python tools/memcheck.py

It works on a copy of your data folder (an APFS clone: instant, no extra disk space) and never
writes to the real one: it loads the search service (model + vectors), reloads the index 10
times, runs a few searches, then runs a quick index update on the copy, and deletes the copy.
The backend defaults to the one the index was built with, so the copy is never rebuilt.
Background: on 2026-11-09 the server had grown to 5.7 GB in an hour and helped freeze a Mac,
and an earlier version of this script ran the indexer on the real index and wiped it.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# MB. Measured on an M4 with 233k vectors (bge-m3): ONNX server 1.3 GB at start and 1.8 GB after
# reloads, PyTorch server 3.3 / 3.4 GB, indexer peak 1.9 GB.
BUDGET = {
    "onnx": {"server_start": 2200, "server_after_reloads": 2600, "reload_growth": 600, "indexer_peak": 3000},
    "torch": {"server_start": 4000, "server_after_reloads": 4300, "reload_growth": 400, "indexer_peak": 3000},
}

CHILD = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from semsearch import memguard, config
from semsearch.search import Searcher
s = Searcher(); start = memguard.footprint_mb()
s.reload(force=True); first = memguard.footprint_mb()
for _ in range(10):
    s.reload(force=True)
after = memguard.footprint_mb()
for q in ["project report", "invoice", "meeting notes", "期中報告"]:
    s.search(q, n=10, rerank=False)
print(json.dumps({"backend": config.embed_backend(), "server_start": start,
                  "server_after_reloads": max(after, memguard.footprint_mb()),
                  "reload_growth": after - first}))
"""


def _copy_data(src: Path) -> Path:
    """Clone the index and settings into a temporary folder; models are shared read-only."""
    dst = Path(tempfile.mkdtemp(prefix="semsearch-memcheck-"))
    for name in ("index.db", "index.db-wal", "index.db-shm", "config.json", "opens.db"):
        if (src / name).exists():
            subprocess.run(["cp", "-c", str(src / name), str(dst / name)], check=True)
    return dst


def main():
    real = Path(os.environ.get("SEMSEARCH_DATA", Path.home() / ".semsearch"))
    if not (real / "index.db").exists():
        sys.exit(f"memcheck: no index in {real}")
    before = (real / "index.db").stat()
    data = _copy_data(real)
    try:
        run(data, real)
    finally:
        shutil.rmtree(data, ignore_errors=True)
        after = (real / "index.db").stat()
        if (after.st_ino, after.st_size) != (before.st_ino, before.st_size):
            print("memcheck: WARNING the real index changed while it ran (another indexer run?)")


def run(data: Path, real: Path):
    env = dict(os.environ)
    env["SEMSEARCH_DATA"] = str(data)
    env.setdefault("SEMSEARCH_MODELS", str(real / "models"))
    db = sqlite3.connect(f"file:{data / 'index.db'}?mode=ro", uri=True)
    built = db.execute("SELECT v FROM meta WHERE k='backend'").fetchone()
    db.close()
    env.setdefault("SEMSEARCH_EMBED_BACKEND", built[0] if built else "torch")
    out = subprocess.run([sys.executable, "-c", CHILD, str(ROOT)], capture_output=True, text=True,
                         cwd=ROOT, env=env)
    line = next((l for l in out.stdout.splitlines() if l.startswith("{")), None)
    if out.returncode != 0 or not line:
        print(out.stderr[-2000:])
        sys.exit("memcheck: the search service did not load")
    r = json.loads(line)
    t = subprocess.run(["/usr/bin/time", "-l", sys.executable, "-m", "semsearch.indexer", "--quick"],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    m = re.search(r"(\d+)\s+peak memory footprint", t.stderr)
    r["indexer_peak"] = int(m.group(1)) / 2**20 if m else None
    budget = BUDGET.get(r["backend"], BUDGET["torch"])
    failed = False
    print(f"backend: {r['backend']}")
    for key, limit in budget.items():
        v = r.get(key)
        ok = v is not None and v <= limit
        failed |= not ok
        shown = "n/a" if v is None else f"{v:.0f}"
        print(f"  {'OK  ' if ok else 'FAIL'} {key:22s} {shown:>6} MB  (budget {limit} MB)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
