"""Log of files opened from the search panel (kept locally in ~/.semsearch/opens.db), used to
move frequently opened files up in the results.

The log doubles as a source of real evaluation queries: query → the file actually opened.
"""
import re
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()
_cache = {"t": 0.0, "data": {}}


def _db():
    config.DATA_DIR.mkdir(exist_ok=True)
    db = sqlite3.connect(config.DATA_DIR / "opens.db", timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS opens(path TEXT, query TEXT, ts REAL)")
    return db


def norm(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def record(path: str, query: str = ""):
    with _lock:
        db = _db()
        db.execute("INSERT INTO opens VALUES(?, ?, ?)", (path, norm(query), time.time()))
        db.commit()
        db.close()
        _cache["t"] = 0.0


def load(max_age=60):
    """Return {path: (times opened, {normalized queries})}, re-read at most every max_age seconds."""
    with _lock:
        if time.time() - _cache["t"] < max_age:
            return _cache["data"]
        data = {}
        try:
            db = _db()
            for path, query in db.execute("SELECT path, query FROM opens"):
                count, queries = data.get(path, (0, set()))
                queries.add(query)
                data[path] = (count + 1, queries)
            db.close()
        except sqlite3.Error:
            pass
        _cache.update(t=time.time(), data=data)
        return data
