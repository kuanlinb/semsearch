import os
import sqlite3

from semsearch import config, indexer
from semsearch.search import Searcher


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
