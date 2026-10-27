"""Folder grouping, usage-based ranking, the /opened endpoint, the remote reranker and OCR."""
import http.client
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from semsearch import config, indexer, search, server, usage
from semsearch.search import Searcher, _group_by_folder

REPO = Path(__file__).resolve().parent.parent
PLAN = "Project plan with milestones, budget and the team schedule for the spring term. " * 3


def _hit(path, is_dir=False, match="name", ext=None):
    return {"path": path, "name": os.path.basename(path), "is_dir": is_dir, "match": match,
            "ext": ext if ext is not None else os.path.splitext(path)[1]}


# ---- grouping ----

def test_group_by_folder_folds_later_files_into_the_first():
    res = _group_by_folder([
        _hit("/a/x.pdf"), _hit("/b/y.pdf"), _hit("/a/z.pdf"), _hit("/a/sub", is_dir=True),
        _hit("/Applications/Foo.app", ext=".app"), _hit("/Applications/Bar.app", ext=".app"),
        _hit("/a/w.md"),
    ])
    assert [r["path"] for r in res] == ["/a/x.pdf", "/b/y.pdf", "/a/sub",
                                        "/Applications/Foo.app", "/Applications/Bar.app"]
    assert [g["path"] for g in res[0]["group"]] == ["/a/z.pdf", "/a/w.md"]
    assert res[1]["group"] == [] and res[2]["group"] == []
    assert "group" not in res[0]["group"][0]


def test_group_size_is_capped():
    res = _group_by_folder([_hit(f"/a/{i}.txt") for i in range(50)], max_group=30)
    assert len(res) == 1 and len(res[0]["group"]) == 30


def test_search_groups_same_folder(index_env):
    (index_env / "home" / "kitchen_renovation_budget.md").write_text(
        "Kitchen renovation budget: cabinets, countertops and labor. " * 3)
    indexer.run(workers=1)
    s = Searcher()
    flat = [r["name"] for r in s.search("kitchen renovation", n=10, group=False)["results"]]
    assert {"kitchen_renovation_plan.md", "kitchen_renovation_budget.md"} <= set(flat)
    grouped = s.search("kitchen renovation", n=10)["results"]
    heads = [r for r in grouped if r["name"].startswith("kitchen_renovation")]
    assert len(heads) == 1
    assert heads[0]["group"][0]["name"].startswith("kitchen_renovation")


# ---- usage-based ranking ----

def _two_plans(root):
    (root / "home" / "project_plan_alpha.md").write_text(PLAN)
    (root / "finance" / "project_plan_beta.md").write_text(PLAN)


def _plan_order(s, q="project plan"):
    return [r["name"] for r in s.search(q, n=10, group=False)["results"] if r["name"].startswith("project_plan")]


def test_opened_files_move_up(index_env):
    _two_plans(index_env)
    indexer.run(workers=1)
    s = Searcher()
    before = _plan_order(s)
    assert len(before) == 2
    second = before[1]
    usage.record(str(next(index_env.rglob(second))), "Project   plan")  # normalized like the query
    after = _plan_order(s)
    assert after[0] == second


def test_recently_used_files_move_up(index_env, monkeypatch):
    _two_plans(index_env)
    indexer.run(workers=1)
    second = _plan_order(Searcher())[1]
    path = str(next(index_env.rglob(second)))
    monkeypatch.setattr(indexer, "_recently_used", lambda days: [path] if days == 7 else [])
    indexer.run(workers=1)
    db = sqlite3.connect(config.DB_PATH)
    assert [r[0] for r in db.execute("SELECT path FROM usage")] == [path]
    db.close()
    assert _plan_order(Searcher())[0] == second


def test_failed_spotlight_keeps_previous_usage(index_env, monkeypatch):
    path = str(index_env / "home" / "kitchen_renovation_plan.md")
    monkeypatch.setattr(indexer, "_recently_used", lambda days: [path])
    indexer.run(workers=1)
    monkeypatch.setattr(indexer, "_recently_used", lambda days: None)
    indexer.run(workers=1)
    db = sqlite3.connect(config.DB_PATH)
    assert db.execute("SELECT count(*) FROM usage").fetchone()[0] == 1
    db.close()


# ---- /opened endpoint ----

@pytest.fixture
def service(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = srv.server_address[1]
    monkeypatch.setenv("SEMSEARCH_PORT", str(port))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield port
    srv.shutdown()
    srv.server_close()


def _post(port, path, body, headers):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("POST", path, body=body, headers=headers)
    r = c.getresponse()
    out = r.status, r.read()
    c.close()
    return out


def test_opened_endpoint_records_round_trip(index_env, service):
    body = json.dumps({"path": "/tmp/report.pdf", "query": "  The Report "})
    status, _ = _post(service, "/opened", body, {"Content-Type": "application/json", "X-SemSearch": "1"})
    assert status == 200
    assert usage.load()["/tmp/report.pdf"] == (1, {"the report"})
    # the custom header is required, like /reindex
    status, _ = _post(service, "/opened", body, {"Content-Type": "application/json"})
    assert status == 403
    status, _ = _post(service, "/opened", "not json", {"X-SemSearch": "1"})
    assert status == 400
    status, _ = _post(service, "/opened", json.dumps({"query": "x"}), {"X-SemSearch": "1"})
    assert status == 400
    assert usage.load()["/tmp/report.pdf"][0] == 1


# ---- remote reranker ----

class _Reranker(BaseHTTPRequestHandler):
    """Prefers texts mentioning "bank"; optionally slow."""
    delay = 0.0
    calls = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).calls += 1
        time.sleep(self.delay)
        data = json.dumps({"scores": [100.0 if "bank" in t else 0.0 for t in body["texts"]]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _start_reranker(delay=0.0):
    _Reranker.delay, _Reranker.calls = delay, 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Reranker)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _use_remote(port):
    cfg = config.DATA_DIR / "config.json"
    c = json.loads(cfg.read_text())
    c["remote_reranker"] = f"http://127.0.0.1:{port}"
    cfg.write_text(json.dumps(c))


def test_remote_reranker_used_when_up_and_skipped_fast_when_down(index_env):
    indexer.run(workers=1)
    srv = _start_reranker()
    port = srv.server_address[1]
    _use_remote(port)
    s = Searcher()
    fast = s.search("kitchen renovation plan", n=5, rerank=False)
    assert fast["reranked"] is False and fast["results"][0]["name"] == "kitchen_renovation_plan.md"
    res = s.search("kitchen renovation plan", n=5)
    assert res["reranked"] is True and _Reranker.calls == 1
    assert res["results"][0]["name"] == "bank_statement_2026.txt"  # the mock's preference won

    srv.shutdown()
    srv.server_close()
    t = time.time()
    res = s.search("kitchen renovation plan", n=5)
    assert res["reranked"] is False and time.time() - t < 2
    assert res["results"][0]["name"] == "kitchen_renovation_plan.md"
    assert s.remote_down_until > time.time() + 10  # backs off instead of retrying every query


def test_remote_reranker_that_is_not_up_yet_never_slows_a_search(index_env, monkeypatch):
    # Right after login or wake the SSH tunnel is not there yet: searches use the fast order
    # without waiting, and the background check picks the reranker up once it answers
    indexer.run(workers=1)
    _Reranker.delay, _Reranker.calls = 0.0, 0
    monkeypatch.setattr(search, "REMOTE_PROBE_EVERY", 0.2)
    monkeypatch.setattr(search, "REMOTE_BACKOFF", 0)
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    _use_remote(port)
    s = Searcher()
    t = time.time()
    res = s.search("kitchen renovation plan", n=5)
    assert res["reranked"] is False and time.time() - t < 1 and _Reranker.calls == 0
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Reranker)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        deadline = time.time() + 5
        while not s.remote_ok and time.time() < deadline:
            time.sleep(0.1)
        assert s.search("kitchen renovation plan", n=5)["reranked"] is True
    finally:
        srv.shutdown()
        srv.server_close()


def test_slow_remote_reranker_times_out(index_env, monkeypatch):
    indexer.run(workers=1)
    monkeypatch.setattr(search, "REMOTE_TIMEOUT", 0.5)
    srv = _start_reranker(delay=3)
    _use_remote(srv.server_address[1])
    try:
        s = Searcher()
        t = time.time()
        res = s.search("kitchen renovation plan", n=5)
        assert res["reranked"] is False and time.time() - t < 2
    finally:
        srv.shutdown()
        srv.server_close()


# ---- OCR ----

def _text_png(path, text):
    """A screenshot-like image. The helper skips images with fewer than 3 lines of text."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1400, 600), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 52)
    for i, line in enumerate([text, "Total due: 1,250 USD by March 31", "Payment by bank transfer",
                              "Thank you for your business"]):
        draw.text((60, 70 + 120 * i), line, fill="black", font=font)
    img.save(str(path))


def _scanned_pdf(path, png):
    from PIL import Image
    Image.open(png).convert("RGB").save(str(path), "PDF", resolution=144)  # an image only: no text layer


def _ocr_state(name):
    db = sqlite3.connect(config.DB_PATH)
    r = db.execute("SELECT ocr_state, (SELECT count(*) FROM chunks c WHERE c.file_id = f.id AND c.kind = 1) "
                   "FROM files f WHERE name=?", (name,)).fetchone()
    db.close()
    return r


def test_ocr_skipped_cleanly_without_helper(index_env, tmp_path):
    png = index_env / "home" / "whiteboard.png"
    _text_png(png, "Consulting invoice for the website redesign")
    _scanned_pdf(index_env / "home" / "scanned_contract.pdf", png)
    assert not indexer.OCR_BIN.exists()
    indexer.run(workers=1)
    assert _ocr_state("whiteboard.png") == (1, 0)          # queued, waiting for the helper
    assert _ocr_state("scanned_contract.pdf") == (1, 0)    # no text layer: queued too
    assert _ocr_state("kitchen_renovation_plan.md")[0] == 0


@pytest.fixture(scope="session")
def ocr_helper(tmp_path_factory):
    if sys.platform != "darwin" or not shutil.which("swiftc") or not shutil.which("taskpolicy"):
        pytest.skip("needs macOS with swiftc")
    built = REPO / "bin" / "semsearch-ocr"
    src = REPO / "mac" / "ocr.swift"
    if built.exists() and built.stat().st_mtime >= src.stat().st_mtime:
        return built
    out = tmp_path_factory.mktemp("bin") / "semsearch-ocr"
    r = subprocess.run(["swiftc", str(src), "-o", str(out)], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        pytest.skip("could not compile mac/ocr.swift: " + r.stderr[-500:])
    return out


def test_ocr_adds_content_chunks(index_env, monkeypatch, ocr_helper):
    monkeypatch.setattr(indexer, "OCR_BIN", ocr_helper)
    png = index_env / "home" / "whiteboard.png"
    _text_png(png, "Consulting invoice for the website redesign")
    _scanned_pdf(index_env / "finance" / "scanned_contract.pdf", png)
    (index_env / "finance" / "holiday_photo.png").write_bytes(b"not really an image")
    indexer.run(workers=1)
    state, chunks = _ocr_state("whiteboard.png")
    assert state == 2 and chunks >= 1
    state, chunks = _ocr_state("scanned_contract.pdf")
    assert state == 2 and chunks >= 1
    assert _ocr_state("holiday_photo.png") == (2, 0)  # unreadable: done, no text
    hits = Searcher().search("consulting invoice website redesign", n=5, group=False)["results"]
    top = {h["name"]: h for h in hits[:2]}
    assert set(top) == {"whiteboard.png", "scanned_contract.pdf"}
    assert all(h["match"] == "content" for h in top.values())
    # a second run has nothing left to OCR
    indexer.run(workers=1)
    assert _ocr_state("whiteboard.png")[0] == 2


def test_ocr_yields_to_new_files(index_env, monkeypatch, ocr_helper):
    monkeypatch.setattr(indexer, "OCR_BIN", ocr_helper)
    _text_png(index_env / "home" / "whiteboard.png", "Consulting invoice for the website redesign")
    indexer.run(workers=1, limit=10)  # --limit skips OCR; the image stays queued
    assert _ocr_state("whiteboard.png")[0] == 1
    indexer.WAKE.touch()  # what the service does when the watcher reports new files
    indexer.run_ocr(indexer.connect(), config.load(), {}, [], lambda: None, lambda: None, [0.0], [])
    assert _ocr_state("whiteboard.png")[0] == 1  # paused before touching it
