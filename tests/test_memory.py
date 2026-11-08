"""Memory regressions: a long-running search server must not grow with every index reload.

2026-11-09: the server reached 5.7 GB after an hour because each reload kept extra copies of
the vectors and cached GPU memory was never returned. This test cannot use the GPU (CI has
none), but it catches the Python side: old matrices or row copies kept alive across reloads.
"""
import sqlite3
import sys

import numpy as np
import pytest

from semsearch import config, indexer, memguard
from semsearch.search import Searcher

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="footprint is read with macOS libproc")

ROWS, DIM = 40000, 1024  # 80 MB of float16 vectors, enough to see a copy kept per reload


def test_footprint_reads_this_process():
    mb = memguard.footprint_mb()
    assert mb is not None and 5 < mb < 100000


def test_reloads_do_not_keep_growing(index_env):
    indexer.run(full=True)
    db = sqlite3.connect(config.DB_PATH)
    fid = db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
    vec = np.random.default_rng(0).standard_normal(DIM).astype(np.float16).tobytes()
    db.execute("DELETE FROM chunks")
    db.executemany("INSERT INTO chunks(file_id, kind, text, vec) VALUES(?,?,?,?)",
                   ((fid, 0, f"t{i}", vec) for i in range(ROWS)))
    db.commit()
    db.close()
    s = Searcher()
    s.reload(force=True)  # the first reload may grow the allocator's pools once
    base = memguard.footprint_mb()
    for _ in range(10):
        s.reload(force=True)
    grown = memguard.footprint_mb() - base
    matrix_mb = ROWS * DIM * 2 / 2**20
    # Measured: about 1 MB now; 0.1.3 grew about 81 MB (one matrix kept per reload)
    assert grown < matrix_mb / 2, f"grew {grown:.0f} MB over 10 reloads (matrix is {matrix_mb:.0f} MB)"


def test_memguard_stops_the_indexer_and_restarts_the_server_once(tmp_path, monkeypatch):
    import time
    monkeypatch.setattr(memguard, "_state_path", lambda: tmp_path / "memguard.json")
    monkeypatch.setattr(memguard, "_notify", lambda m: events.append("notify"))
    events = []
    memguard.start("indexer", 1, every=0.05, log=lambda m: None, exit=lambda c: events.append(c))
    time.sleep(0.3)
    assert events and events[0] == 4
    events.clear()
    stop = []
    memguard.start("server", 1, every=0.05, min_uptime=0, log=lambda m: None,
                   exit=lambda c: (stop.append(c), time.sleep(60)))  # a real exit never returns
    time.sleep(0.3)
    assert stop == [75]
    later = []
    memguard.start("server", 1, every=0.05, min_uptime=0, log=lambda m: later.append(m),
                   exit=lambda c: later.append(("exit", c)))
    time.sleep(0.3)
    assert not any(isinstance(x, tuple) for x in later), "must not restart twice within an hour"
    assert sum("not restarting" in x for x in later if isinstance(x, str)) == 1
