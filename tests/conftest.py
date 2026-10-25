"""Tests run against a throwaway data dir and a tiny fake embedding model (no downloads)."""
import hashlib
import os
import tempfile

import numpy as np
import pytest

os.environ["SEMSEARCH_DATA"] = tempfile.mkdtemp(prefix="semsearch-test-")

from semsearch import config, embed, indexer, usage  # noqa: E402

DIM = 64


def fake_encode(texts, kind="passage", batch_size=64):
    """Bag of character trigrams hashed into DIM buckets: similar strings → similar vectors."""
    out = np.zeros((len(texts), DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        t = t.lower()
        for j in range(max(1, len(t) - 2)):
            h = int(hashlib.md5(t[j:j + 3].encode()).hexdigest(), 16)
            out[i, h % DIM] += 1
        out[i] /= np.linalg.norm(out[i]) or 1
    return out.astype(np.float16)


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    monkeypatch.setattr(embed, "get_model", lambda name: setattr(embed, "_name", name))
    monkeypatch.setattr(embed, "encode", fake_encode)
    embed._name = "fake"
    # No real Spotlight usage data and no OCR helper unless a test opts in
    monkeypatch.setattr(indexer, "_recently_used", lambda days: [])
    monkeypatch.setattr(indexer, "OCR_BIN", config.DATA_DIR / "no-such-ocr-helper")


@pytest.fixture
def index_env(tmp_path):
    """A small folder tree plus a config pointing at it; the DB starts empty."""
    root = tmp_path / "files"
    (root / "home").mkdir(parents=True)
    (root / "home" / "kitchen_renovation_plan.md").write_text(
        "Kitchen renovation plan: cabinets, countertops and lighting. " * 3)
    (root / "finance").mkdir()
    (root / "finance" / "bank_statement_2026.txt").write_text(
        "Monthly bank statement with deposits and withdrawals for February. " * 3)
    for f in ("index.db", "index.db-wal", "index.db-shm", "opens.db", "wake"):
        (config.DATA_DIR / f).unlink(missing_ok=True)
    usage._cache.update(t=0.0, data={})
    (config.DATA_DIR / "config.json").write_text(
        '{"roots": ["%s"], "hot_roots": [], "model": "fake"}' % root)
    return root
