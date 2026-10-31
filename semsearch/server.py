"""Long-running search service: keeping the model in memory makes each search fast.

  GET  /search?q=...&n=20   search, returns JSON (rerank=0 skips the optional reranker,
                            group=0 turns off folding files from the same folder,
                            cond=0 ignores time and source words, e.g. after the panel's ✕)
  GET  /status              index status (no_access lists folders macOS has not granted)
  POST /reindex             update the index in the background
  POST /opened              {"path": ..., "query": ...}: log a file opened from the panel
  GET  /                    minimal web UI
POST requests need the header "X-SemSearch: 1".
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config, usage
from .search import Searcher

ROOT = Path(__file__).resolve().parent.parent
searcher = None
search_lock = threading.Lock()
indexer_proc = None
_children = []  # helper processes to stop when the service stops (indexer, file watcher, SSH tunnel)


def _spawn(*args, **kw):
    proc = subprocess.Popen(*args, **kw)
    _children.append(proc)
    _children[:] = [p for p in _children if p.poll() is None]
    return proc


def _stop(signum=None, frame=None):
    """Quitting the app sends SIGTERM: stop the helpers too, so a long indexing run doesn't outlive it."""
    procs = list(_children)
    for p in procs:
        if p.poll() is None:
            p.terminate()
    deadline = time.time() + 3
    for p in procs:
        try:
            p.wait(max(0.0, deadline - time.time()))
        except subprocess.TimeoutExpired:
            p.kill()
    os._exit(0)


def start_indexer(quick=False, paths=None):
    global indexer_proc
    if indexer_proc and indexer_proc.poll() is None:
        return False
    log = open(config.DATA_DIR / "indexer.log", "a")
    indexer_proc = _spawn(
        ["nice", "-n", "15", sys.executable, "-m", "semsearch.indexer"] + (["--quick"] if quick else [])
        + (["--paths", *paths] if paths else []),
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _trusted(self):
        """Only answer requests addressed to this loopback port: blocks DNS-rebinding pages."""
        port = config.load()["port"]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def do_GET(self):
        if not self._trusted():
            self._send(403, {"error": "forbidden"})
            return
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if searcher is None and u.path in ("/search", "/status"):
            self._send(503, {"error": "starting up, try again in a few seconds"})
            return
        if u.path == "/search":
            q = qs.get("q", [""])[0]
            try:
                n = max(1, min(int(qs.get("n", ["20"])[0]), 100))
            except ValueError:
                n = 20
            kind = qs.get("kind", [None])[0]
            rerank = qs.get("rerank", ["1"])[0] != "0"
            group = qs.get("group", ["1"])[0] != "0"
            cond = qs.get("cond", ["1"])[0] != "0"
            try:
                with search_lock:
                    res = searcher.search(q, n=n, kind=kind, rerank=rerank, group=group, cond=cond)
            except Exception as e:
                self._send(500, {"error": str(e), "results": [], "ms": 0})
                return
            self._send(200, res)
        elif u.path == "/status":
            st = searcher.status()
            st["indexing"] = bool(indexer_proc and indexer_proc.poll() is None) or _lock_held()
            if not st["indexing"]:
                st.pop("progress", None)  # left behind by an interrupted run
            st["no_access"] = [r for r, v in dict(_access).items() if v != "ok"]  # probe threads add keys
            self._send(200, st)
        elif re.fullmatch(r"/l10n/[A-Za-z-]+\.json", u.path) and (ROOT / u.path[1:]).is_file():
            self._send(200, (ROOT / u.path[1:]).read_bytes())
        elif u.path in ("/", "/index.html"):
            self._send(200, (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        # A custom header forces a CORS preflight, so other web pages cannot trigger this
        if not self._trusted() or self.headers.get("X-SemSearch") != "1":
            self._send(403, {"error": "forbidden"})
            return
        if urlparse(self.path).path == "/opened":
            # Remember which file was opened for which query (stored locally only)
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                body = json.loads(self.rfile.read(min(n, 100_000)) or b"{}")
                usage.record(str(body["path"]), str(body.get("query", "")))
                self._send(200, {"ok": True})
            except (ValueError, KeyError, TypeError):
                self._send(400, {"error": "bad request"})
            return
        if urlparse(self.path).path == "/reindex":
            self._send(200, {"started": start_indexer()})
        else:
            self._send(404, {"error": "not found"})


def _lock_held():
    import fcntl
    try:
        fh = open(config.DATA_DIR / "indexer.lock", "w")
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()
        return False
    except BlockingIOError:
        return True
    except OSError:
        return False


QUICK_EVERY = 30 * 60  # the indexer upgrades a quick run to a full scan when the last one is >6h old


QUIET = 30  # seconds without file changes (e.g. a finished download) before indexing new files
MAX_WAIT = 300  # but no longer than this while something keeps writing
MIN_GAP = 60  # between two runs the watcher starts: each run loads the model
_last_watch_run = [0.0]

_changed = [0.0]  # time of the last file change reported by the watcher
_first_change = [0.0]  # time of the oldest change not indexed yet
_changed_dirs = set()  # folders to rescan (indexer.change_target)
_changed_lock = threading.Lock()
_access = {}      # root -> "ok" / "denied" / "waiting" (macOS folder permission)
_probes = {}


def _check_access():
    """macOS asks the user before an app may read Documents / Downloads / Desktop. Until they
    click Allow, reading such a folder hangs or fails and the index silently stops updating,
    so the menu shows a warning."""
    for root in config.load()["roots"]:
        prev = _probes.get(root)
        if prev and prev.is_alive():  # the last probe is still stuck: waiting for the prompt
            _access[root] = "waiting"
            continue
        result = ["waiting"]

        def probe(r=root, out=result):
            try:
                os.listdir(r)
                out[0] = "ok"
            except PermissionError:
                out[0] = "denied"
            except OSError:
                out[0] = "ok"  # missing folders etc. are not a permission problem
        t = threading.Thread(target=probe, daemon=True)
        _probes[root] = t
        t.start()
        t.join(5)
        _access[root] = result[0]


def _start_fs_watch():
    """Watch every indexed folder and rescan the folders that changed ~30 s after the last
    change, so new, edited, moved and deleted files show up without waiting for a scan.

    Uses a separate helper (bin/semsearch-fswatch, macOS FSEvents) that prints a line per
    change. Python's watchdog is not used: it can hold the GIL inside native code and
    freeze the whole service.
    """
    from . import indexer
    exe = ROOT / "bin" / "semsearch-fswatch"
    cfg = config.load()
    # names_only_roots (code projects) change all the time: the 30-minute quick run covers them
    roots = [r for r in indexer._dedupe_roots(cfg["roots"]) if os.path.isdir(r)
             and not indexer._under(r, cfg["names_only_roots"])]
    indexer._exclude_substrings[:] = cfg.get("exclude_substrings", [])
    if not exe.exists() or not roots:
        return
    while True:
        try:
            proc = _spawn([str(exe), *roots], stdout=subprocess.PIPE, text=True)
            for line in proc.stdout:
                target = indexer.change_target(line.rstrip("\n"), roots)
                if target is None:
                    continue  # hidden files, packages, build output: the index never looks there
                with _changed_lock:
                    _changed_dirs.add(target)
                    _changed[0] = time.time()
                    _first_change[0] = _first_change[0] or _changed[0]
        except OSError:
            pass
        time.sleep(30)  # the helper exited unexpectedly: restart it after a pause


def _tunnel_port(url):
    try:
        return urlparse(url).port or 8798
    except ValueError:
        return 8798


def _keep_tunnel(host, port):
    """Keep an SSH tunnel (local port → 127.0.0.1:port on the remote host) open for the
    remote reranker, reconnecting when it drops."""
    while True:
        try:
            _spawn(["ssh", "-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30",
                    "-o", "BatchMode=yes", "-L", f"{port}:127.0.0.1:{port}", host],
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        except OSError:
            pass
        time.sleep(30)


def _watch():
    # Reload in the background after the index changes, and schedule index updates
    next_quick = time.time() + 20  # first run soon: builds the index on a fresh install
    next_access = 0.0
    wake = config.DATA_DIR / "wake"
    while True:
        time.sleep(10)
        if time.time() >= next_access:
            threading.Thread(target=_check_access, daemon=True).start()
            # recheck after 30 s while a folder is still blocked, so the warning clears soon after the user allows it
            next_access = time.time() + (30 if any(v != "ok" for v in dict(_access).values()) else 300)
        busy = _lock_held()
        # While the indexer runs, reload at most every 5 minutes to keep the GPU free
        if busy:
            searcher.maybe_reload(min_interval=300)
        else:
            searcher.maybe_reload()
        if _changed[0] and busy:
            wake.touch()  # ask the running indexer to pause OCR; the change is kept for later
        now = time.time()
        due = _changed[0] and (now - _changed[0] > QUIET or now - _first_change[0] > MAX_WAIT)
        if due and not busy and now - _last_watch_run[0] > MIN_GAP:
            with _changed_lock:
                dirs = sorted(_changed_dirs)
            if start_indexer(paths=dirs):
                _last_watch_run[0] = now
                with _changed_lock:
                    _changed_dirs.difference_update(dirs)
                    if not _changed_dirs:
                        _changed[0] = _first_change[0] = 0.0
        elif time.time() >= next_quick and start_indexer(quick=True):
            next_quick = time.time() + QUICK_EVERY


def main():
    global searcher
    # Debugging: `kill -USR1 <pid>` writes every thread's current stack to server.log
    import faulthandler
    import signal
    faulthandler.register(signal.SIGUSR1, all_threads=True)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    cfg = config.load()
    config.DATA_DIR.mkdir(exist_ok=True)
    # Bind the port before loading the model: a second copy fails fast instead of loading for nothing
    srv = ThreadingHTTPServer(("127.0.0.1", cfg["port"]), Handler)
    # Serve requests only after the model is loaded: loading imports a lot, and a request
    # thread importing at the same time can deadlock on the import lock. Connections made
    # meanwhile wait in the listen queue.
    if not config.DB_PATH.exists():
        from . import indexer
        indexer.connect().close()
    s = Searcher()
    s.search("warm up")
    searcher = s
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # The watcher walks the watched trees when it starts; keep that off the main thread
    threading.Thread(target=_start_fs_watch, daemon=True).start()
    if cfg.get("remote_reranker_ssh") and cfg.get("remote_reranker"):
        threading.Thread(target=_keep_tunnel, daemon=True,
                         args=(cfg["remote_reranker_ssh"], _tunnel_port(cfg["remote_reranker"]))).start()
    print(f"semsearch ready on http://127.0.0.1:{cfg['port']}", flush=True)
    _watch()


if __name__ == "__main__":
    main()
