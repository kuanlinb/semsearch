import os
import json
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


def _mark_stale():
    db = sqlite3.connect(config.DB_PATH)
    assert db.execute("SELECT v FROM meta WHERE k='backend'").fetchone() == ("onnx",)
    db.execute("UPDATE files SET name='stale' WHERE name='kitchen_renovation_plan.md'")
    db.commit()
    db.close()


def test_switching_backend_in_config_rebuilds_the_index(index_env):
    indexer.run(workers=1)
    _mark_stale()
    cfg = json.loads((config.DATA_DIR / "config.json").read_text())
    cfg["embed_backend"] = "torch"
    (config.DATA_DIR / "config.json").write_text(json.dumps(cfg))
    indexer.run(workers=1)
    assert "stale" not in names() and "kitchen_renovation_plan.md" in names()


def test_a_one_off_backend_never_wipes_the_index(index_env, monkeypatch):
    """2026-11-09: a test run with SEMSEARCH_EMBED_BACKEND wiped a real index (days of OCR)."""
    indexer.run(workers=1)
    _mark_stale()
    monkeypatch.setenv("SEMSEARCH_EMBED_BACKEND", "torch")
    indexer.run(workers=1)
    assert "stale" in names(), "the index must be left alone"
    db = sqlite3.connect(config.DB_PATH)
    assert db.execute("SELECT v FROM meta WHERE k='backend'").fetchone() == ("onnx",)


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


def _write_config(**extra):
    cfg = json.loads((config.DATA_DIR / "config.json").read_text())
    cfg.update(extra)
    (config.DATA_DIR / "config.json").write_text(json.dumps(cfg))


def test_a_string_where_a_list_belongs_is_one_item(index_env):
    """2026-11-10: "exclude_substrings": "secret" excluded every path with an "s" or a "/",
    and the next run deleted the whole index."""
    indexer.run(workers=1)
    _write_config(exclude_substrings="finance/bank")
    indexer.run(workers=1)
    n = names()
    assert "kitchen_renovation_plan.md" in n and "bank_statement_2026.txt" not in n
    _write_config(exclude_substrings=[""], extra_roots=None)  # "" would match every path
    assert config.load()["exclude_substrings"] == []


def test_a_broken_config_never_touches_the_index(index_env):
    indexer.run(workers=1)
    before = names()
    path = config.DATA_DIR / "config.json"
    path.write_text(path.read_text()[:-1] + ', "exclude_substrings": ["home"],}')  # trailing comma
    assert config.load()["config_problems"]
    indexer.run(workers=1)
    assert names() == before
    broken = '{"roots": 5, "model": "fake"}'
    path.write_text(broken)
    assert any('"roots"' in p for p in config.load()["config_problems"])
    indexer.run(workers=1)
    assert names() == before


def test_wrong_types_are_ignored_not_used(tmp_path):
    (config.DATA_DIR / "config.json").write_text(
        '{"roots": "~/Notes", "port": "8800", "conditions": "yes", "max_server_mb": 3000, "reranker": false}')
    cfg = config.load()
    assert cfg["roots"] == [os.path.expanduser("~/Notes")]
    assert cfg["port"] == 8799 and cfg["conditions"] is True and cfg["max_server_mb"] == 3000
    assert cfg["reranker"] == "" and len(cfg["config_problems"]) == 2
    # null or an unknown backend must not switch backends (that rebuilds the whole index)
    for bad in ['{"embed_backend": null}', '{"embed_backend": "Torch"}', '{"embed_backend": false}',
                '{"model": null}', '{"roots": null}', '{"port": 8799.5}', '{"conditions": null}']:
        (config.DATA_DIR / "config.json").write_text(bad)
        assert config.load()["config_problems"], bad
    (config.DATA_DIR / "config.json").write_text('{"port": 8800.0, "extra_roots": null, "conditions": 0}')
    cfg = config.load()
    assert not cfg["config_problems"] and cfg["port"] == 8800 and cfg["conditions"] is False


def test_a_scan_that_finds_most_files_gone_waits_for_a_second_one(index_env, monkeypatch):
    many = index_env / "many"
    many.mkdir()
    for i in range(30):
        (many / f"note_{i}.txt").write_text("x")
    monkeypatch.setattr(indexer, "MASS_REMOVAL_MIN", 10)
    indexer.run(workers=1)
    assert "note_7.txt" in names()
    for f in many.iterdir():
        f.unlink()
    indexer.run(workers=1)
    assert "note_7.txt" in names(), "a sudden mass removal is postponed"
    # A quick run of other folders in between neither confirms nor cancels it
    _write_config(hot_roots=[str(index_env / "home")])
    indexer.run(workers=1, quick=True)
    assert "note_7.txt" in names()
    db = sqlite3.connect(config.DB_PATH)
    db.execute("UPDATE files SET missing_since = missing_since - 4000 WHERE missing_since IS NOT NULL")
    db.commit()
    db.close()
    indexer.run(workers=1)
    assert "note_7.txt" not in names(), "an hour later the files are still gone: remove them"


def test_a_glitch_never_removes_what_comes_back(index_env, monkeypatch):
    """Only entries missed by two scans an hour apart go; ones found again are unmarked, and
    an old mark elsewhere does not let a new glitch through (second review, 2026-11-10)."""
    import time as _t
    monkeypatch.setattr(indexer, "MASS_REMOVAL_MIN", 10)
    a, b = index_env / "a", index_env / "b"
    for d, n in ((a, 30), (b, 10)):        # a alone is most of the index
        d.mkdir()
        for i in range(n):
            (d / f"{d.name}_{i}.txt").write_text("x")
    indexer.run(workers=1)
    hidden = index_env.parent / "hidden"
    a.rename(hidden)                       # folder a "disappears" (a glitch)
    indexer.run(workers=1)
    assert "a_3.txt" in names()
    hidden.rename(a)                       # back again
    indexer.run(workers=1)
    db = sqlite3.connect(config.DB_PATH)
    assert db.execute("SELECT count(*) FROM files WHERE missing_since IS NOT NULL").fetchone()[0] == 0
    db.close()
    a.rename(hidden)
    b.rename(index_env.parent / "hidden_b")
    indexer.run(workers=1)                 # both missing: marked now, nothing removed
    db = sqlite3.connect(config.DB_PATH)
    db.execute("UPDATE files SET missing_since=? WHERE name LIKE 'a_%'", (_t.time() - 4000,))
    db.commit()
    db.close()
    indexer.run(workers=1)
    n = names()
    assert "a_3.txt" not in n, "missed an hour ago and still missing: removed"
    assert "b_3.txt" in n, "missed for the first time just now: kept"


def test_the_data_folder_is_private(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir(mode=0o755)
    monkeypatch.setattr(config, "DATA_DIR", data)
    old = os.umask(0o022)
    try:
        config.ensure_data_dir()
        assert data.stat().st_mode & 0o777 == 0o700
        (data / "f").write_text("x")
        assert (data / "f").stat().st_mode & 0o077 == 0
    finally:
        os.umask(old)


def test_datasets_are_folded_but_screenshots_and_named_files_are_not(index_env, monkeypatch):
    """2026-11-10: a Desktop folder with 160 screenshots (and one hand-named image) was skipped
    entirely as a "dataset"."""
    monkeypatch.setattr(config, "DATASET_THRESHOLD", 10)
    frames = index_env / "train" / "frames"
    shots = index_env / "Shots"
    frames.mkdir(parents=True)
    shots.mkdir()
    for i in range(20):
        (frames / f"frame_{i:05d}.png").write_bytes(b"x")
        (shots / f"Screenshot 2026-11-{i % 28 + 1:02d} at 10.{i:02d}.32.png").write_bytes(b"x")
        (shots / f"截圖 2026-11-10 上午10.{i:02d}.32.png").write_bytes(b"x")
    (frames / "cover photo.png").write_bytes(b"x")
    (shots / "boarding pass.png").write_bytes(b"x")
    indexer.run(workers=1)
    n = names()
    assert "frame_00007.png" not in n, "machine-named dataset files are folded into the folder"
    assert "cover photo.png" in n, "a file the user named is indexed even inside a dataset"
    assert "Screenshot 2026-11-08 at 10.07.32.png" in n and "截圖 2026-11-10 上午10.07.32.png" in n
    assert "boarding pass.png" in n


def test_desktop_itself_is_never_folded(index_env, monkeypatch):
    monkeypatch.setattr(config, "DATASET_THRESHOLD", 10)
    for i in range(20):
        (index_env / f"IMG_{i:04d}.jpg").write_bytes(b"x")
    _write_config(hot_roots=[str(index_env)])
    indexer.run(workers=1)
    assert "IMG_0007.jpg" in names()


def test_a_query_of_only_a_type_word_lists_that_type(index_env):
    """2026-11-10: "screenshot", "截圖", "pdf", "folder" alone returned no results."""
    (index_env / "Screenshot 2026-11-10 at 10.15.32.png").write_bytes(b"x")
    (index_env / "holiday.jpg").write_bytes(b"x")
    (index_env / "report.pdf").write_bytes(b"%PDF-1.4")
    indexer.run(workers=1)
    s = Searcher()
    for q, want in [("screenshot", {".png", ".jpg"}), ("截圖", {".png", ".jpg"}), ("pdf", {".pdf"})]:
        got = s.search(q, n=5, group=False)["results"]
        assert got and all(os.path.splitext(r["path"])[1] in want for r in got), q
    assert s.search("screenshot", n=5, group=False)["results"][0]["name"].startswith("Screenshot")
    folders = s.search("folder", n=5, group=False)["results"]
    assert folders and all(r["is_dir"] for r in folders if r.get("path", "").startswith(str(index_env)))


def test_an_interrupted_model_download_resumes(tmp_path, monkeypatch):
    """A dropped connection continues where it stopped instead of starting the 590 MB over."""
    import hashlib
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from semsearch import embed
    body = bytes(range(256)) * 400
    ranges = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            start = int(self.headers.get("Range", "bytes=0-")[6:].rstrip("-") or 0)
            ranges.append(start)
            part = body[start:]
            self.send_response(206 if start else 200)
            self.send_header("Content-Length", str(len(part)))
            self.end_headers()
            # the first answer breaks off halfway
            self.wfile.write(part[: len(part) // 2] if len(ranges) == 1 else part)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr("time.sleep", lambda s: None)
    try:
        folder = embed._fetch("m", f"http://127.0.0.1:{srv.server_port}/",
                              {"model.onnx": hashlib.sha256(body).hexdigest()})
    finally:
        srv.shutdown()
    assert (folder / "model.onnx").read_bytes() == body
    assert ranges == [0, len(body) // 2], "the second request asks only for the rest"
    assert not (config.DATA_DIR / embed.DOWNLOAD_STATUS).exists()


def test_latest_ranks_the_newest_version_first_however_old(index_env):
    import time as _t
    for name, age in [("resume_v1.txt", 400), ("resume_v2.txt", 90)]:
        p = index_env / name
        p.write_text("Resume: data science, Python, statistics. " * 3)
        os.utime(p, (_t.time() - age * 86400,) * 2)
    indexer.run(workers=1)
    s = Searcher()
    for q in ["latest resume", "最新的 resume"]:
        got = [r["name"] for r in s.search(q, n=5, group=False)["results"]]
        assert got[0] == "resume_v2.txt", (q, got)  # 90 days old: a 30-day filter would drop it


def test_files_found_by_an_interrupted_run_are_unmarked(index_env, monkeypatch):
    """Third review, 2026-11-10: a run that found the files again but stopped before its cleanup
    (memory limit, crash) left the old mark, so the next glitch removed files that exist."""
    import pytest
    monkeypatch.setattr(indexer, "MASS_REMOVAL_MIN", 10)
    a = index_env / "a"
    a.mkdir()
    for i in range(30):
        (a / f"a_{i}.txt").write_text("x")
    indexer.run(workers=1)
    hidden = index_env.parent / "hidden"
    a.rename(hidden)                       # glitch 1: marked
    indexer.run(workers=1)
    hidden.rename(a)                       # back, but this run dies before its cleanup
    orig = indexer.run_ocr

    def crash(*args, **kw):
        raise MemoryError("stopped in the OCR phase")
    monkeypatch.setattr(indexer, "run_ocr", crash)
    with pytest.raises(MemoryError):
        indexer.run(workers=1)
    monkeypatch.setattr(indexer, "run_ocr", orig)
    db = sqlite3.connect(config.DB_PATH)
    db.execute("UPDATE files SET missing_since = missing_since - 4000 WHERE missing_since IS NOT NULL")
    db.commit()
    db.close()
    a.rename(hidden)                       # glitch 2, an hour after glitch 1
    indexer.run(workers=1)
    assert "a_3.txt" in names(), "found again in between: this is a first miss, keep it"
