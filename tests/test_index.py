import os
import sqlite3

import numpy as np

from semsearch import config, indexer
from semsearch.search import Searcher, _scores


def names():
    db = sqlite3.connect(config.DB_PATH)
    out = {r[0] for r in db.execute("SELECT name FROM files")}
    db.close()
    return out


def test_index_and_search(index_env):
    indexer.run(workers=1)
    assert {"kitchen_renovation_plan.md", "bank_statement_2026.txt", "home"} <= names()
    s = Searcher()
    top = s.search("kitchen renovation plan", n=3)["results"]
    assert top[0]["name"] == "kitchen_renovation_plan.md"
    top = s.search("bank statement", n=3)["results"]
    assert top[0]["name"] == "bank_statement_2026.txt"


def test_search_without_pytorch(index_env, monkeypatch):
    """embed_backend "onnx" keeps the vectors in NumPy; results match the PyTorch path."""
    indexer.run(workers=1)
    monkeypatch.setenv("SEMSEARCH_EMBED_BACKEND", "onnx")
    s = Searcher()
    assert isinstance(s.mat, np.ndarray)
    top = s.search("kitchen renovation plan", n=3)["results"]
    assert top[0]["name"] == "kitchen_renovation_plan.md"


def test_blocked_scores_match_matmul():
    mat = np.random.default_rng(0).standard_normal((20000, 16)).astype(np.float16)
    q = mat[123]
    assert np.allclose(_scores(mat, q, block=4096), mat.astype(np.float32) @ q.astype(np.float32), atol=1e-3)


def test_incremental_update_and_deletion(index_env):
    indexer.run(workers=1)
    (index_env / "finance" / "bank_statement_2026.txt").unlink()
    (index_env / "home" / "new_notes.md").write_text("Notes about tiles and paint colors. " * 3)
    indexer.run(workers=1)
    n = names()
    assert "bank_statement_2026.txt" not in n
    assert "new_notes.md" in n


def test_unreadable_folder_keeps_its_entries(index_env):
    indexer.run(workers=1)
    locked = index_env / "home"
    os.chmod(locked, 0)
    try:
        indexer.run(workers=1)
    finally:
        os.chmod(locked, 0o755)
    assert "kitchen_renovation_plan.md" in names()


def test_missing_root_keeps_its_entries(index_env, tmp_path):
    indexer.run(workers=1)
    index_env.rename(tmp_path / "moved")       # e.g. an unmounted drive
    try:
        indexer.run(workers=1)
        assert "bank_statement_2026.txt" in names()
    finally:
        (tmp_path / "moved").rename(index_env)


def test_nested_roots_are_deduplicated():
    assert sorted(indexer._dedupe_roots(["/a/b", "/a", "/a/", "/c"])) == ["/a", "/c"]


def test_exclude_substrings_match_full_paths(index_env):
    cfg = config.DATA_DIR / "config.json"
    cfg.write_text(cfg.read_text()[:-1] + ', "exclude_substrings": ["finance/bank"]}')
    indexer.run(workers=1)
    n = names()
    assert "bank_statement_2026.txt" not in n and "kitchen_renovation_plan.md" in n


def test_extra_roots_are_added(tmp_path, monkeypatch):
    (config.DATA_DIR / "config.json").write_text('{"roots": ["/a"], "extra_roots": ["/b/"]}')
    assert config.load()["roots"] == ["/a", "/b"]


def test_only_web_page_asset_folders_are_skipped():
    from semsearch.indexer import skip_dir
    assert skip_dir("Article_files", {"Article.html", "Article_files"})
    assert skip_dir("page.files", {"page.htm", "page.files"})
    assert not skip_dir("tax_files", {"tax_files", "notes.txt"})
    assert not skip_dir("client_files")
    assert skip_dir("node_modules") and skip_dir(".git")


def test_switching_backend_rebuilds_the_index(index_env, monkeypatch):
    indexer.run(workers=1)
    db = sqlite3.connect(config.DB_PATH)
    assert db.execute("SELECT v FROM meta WHERE k='backend'").fetchone() == ("onnx",)
    db.execute("UPDATE files SET name='stale' WHERE name='kitchen_renovation_plan.md'")
    db.commit()
    monkeypatch.setenv("SEMSEARCH_EMBED_BACKEND", "torch")
    indexer.run(workers=1)
    assert "stale" not in names() and "kitchen_renovation_plan.md" in names()


def test_model_download_is_checked(tmp_path, monkeypatch):
    import hashlib

    import pytest
    from semsearch import embed
    src = tmp_path / "src"
    src.mkdir()
    (src / "model.onnx").write_bytes(b"weights")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    good = hashlib.sha256(b"weights").hexdigest()
    folder = embed._fetch("m", src.as_uri() + "/", {"model.onnx": good})
    assert (folder / "model.onnx").read_bytes() == b"weights"
    with pytest.raises(RuntimeError):
        embed._fetch("bad", src.as_uri() + "/", {"model.onnx": "0" * 64})
    assert not list((tmp_path / "models" / "bad").iterdir())


def test_watched_changes_map_to_folders_to_rescan(tmp_path):
    root = str(tmp_path)
    t = indexer.change_target
    assert t(f"{root}/Notes/a.txt", [root]) == f"{root}/Notes"
    assert t(f"{root}/a.txt", [root]) == root
    assert t(f"{root}/New folder", [root]) == root          # a new folder: its parent finds what it holds
    assert t(f"{root}/Apps/Foo.app/Contents/Info.plist", [root]) == f"{root}/Apps"
    assert t(f"{root}/proj/node_modules/x/index.js", [root]) is None
    assert t(f"{root}/proj/.git/index", [root]) is None
    assert t(f"{root}/Notes/.DS_Store", [root]) is None
    assert t("/elsewhere/a.txt", [root]) is None


def test_rescanning_changed_folders_adds_and_removes_files(index_env):
    indexer.run(workers=1)
    home = index_env / "home"
    (home / "garden_plan.md").write_text("Plant tomatoes and basil along the south fence. " * 3)
    (home / "kitchen_renovation_plan.md").unlink()
    indexer.run(workers=1, paths=[str(home)])
    n = names()
    assert "garden_plan.md" in n and "kitchen_renovation_plan.md" not in n
    assert "home" in n and "bank_statement_2026.txt" in n  # the folder itself and other folders stay
