"""Walk folders, extract text, chunk it, embed it, and store everything in ~/.semsearch/index.db.

Incremental: only files whose size or mtime changed are processed, so reruns take seconds.
Usage: python -m semsearch.indexer [--quick] [--full] [--limit N]
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import apps as appinfo, config, embed, extract

SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
  id INTEGER PRIMARY KEY, path TEXT UNIQUE, name TEXT, parent TEXT, ext TEXT,
  size INTEGER, mtime REAL, is_dir INTEGER, dataless INTEGER, note TEXT,
  seen INTEGER, content_done INTEGER DEFAULT 1, content_tries INTEGER DEFAULT 0,
  ocr_state INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY, file_id INTEGER, kind INTEGER, text TEXT, vec BLOB);
CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, tokenize='trigram');
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS usage(path TEXT PRIMARY KEY, last_used REAL);
"""
KIND_NAME, KIND_CONTENT = 0, 1
# Content chunks are embedded with the file name prepended so they know which document
# they belong to (the database stores the raw chunk).


def connect():
    config.DATA_DIR.mkdir(exist_ok=True)
    db = sqlite3.connect(config.DB_PATH, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    cols = {r[1] for r in db.execute("PRAGMA table_info(files)")}
    if "content_done" not in cols:
        db.execute("ALTER TABLE files ADD COLUMN content_done INTEGER DEFAULT 1")
    if "content_tries" not in cols:
        db.execute("ALTER TABLE files ADD COLUMN content_tries INTEGER DEFAULT 0")
    if "ocr_state" not in cols:  # 0 not needed, 1 waiting for OCR, 2 done
        db.execute("ALTER TABLE files ADD COLUMN ocr_state INTEGER DEFAULT 0")
    return db


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def skip_dir(name: str, siblings=()) -> bool:
    if name in config.EXCLUDE_DIRS or name.startswith("."):
        return True
    for suffix in ("_files", ".files"):
        # asset folder of a "Save Page As" web page: only when the page itself sits next to it
        base = name[:-len(suffix)]
        if name.endswith(suffix) and any(base + x in siblings for x in (".html", ".htm", ".xhtml")):
            return True
    return False


def _excluded(path: str) -> bool:
    return any(s in path for s in _exclude_substrings)


_exclude_substrings = []


def walk(roots, failed=None):
    """Yield (path, stat, is_dir, note). Dataset folders yield only the folder itself.

    Folders that cannot be read (missing, no permission, cloud provider hiccup) are
    recorded in `failed`, so the cleanup step never mistakes them for deleted files.
    """
    failed = failed if failed is not None else []
    for root in roots:
        if not os.path.isdir(root):
            failed.append(root)
            continue
        stack = [root]
        while stack:
            d = stack.pop()
            try:
                entries = list(os.scandir(d))
            except OSError:
                failed.append(d)
                continue
            names = {e.name for e in entries}
            if "pyvenv.cfg" in names:
                continue  # Python virtual environment
            files = [e for e in entries if not e.name.startswith(".")]
            by_ext = {}
            for e in files:
                if e.is_file(follow_symlinks=False):
                    by_ext.setdefault(os.path.splitext(e.name)[1].lower(), []).append(e.name)
            counts = {x: len(v) for x, v in by_ext.items()}
            bulk = {x for x, v in by_ext.items()
                    if len(v) >= config.DATASET_THRESHOLD and x not in config.NEVER_COLLAPSE_EXT
                    and sum(map(_serial, v)) >= config.DATASET_SERIAL_RATIO * len(v)}
            note = ""
            if bulk:
                note = ", ".join(f"{counts[x]} {x or 'extensionless'} files" for x in bulk)
            if d != root:
                try:
                    yield d, os.stat(d, follow_symlinks=False), True, note
                except OSError:
                    pass
            for e in files:
                try:
                    if e.is_symlink() or _excluded(e.path):
                        continue
                    if e.is_dir():
                        ext = os.path.splitext(e.name)[1].lower()
                        if ext in config.BUNDLE_EXT:
                            yield e.path, e.stat(follow_symlinks=False), False, ""
                        elif not skip_dir(e.name, names):
                            stack.append(e.path)
                    elif e.is_file():
                        if os.path.splitext(e.name)[1].lower() in bulk:
                            continue
                        yield e.path, e.stat(follow_symlinks=False), False, ""
                except OSError:
                    failed.append(e.path)
                    continue


def _under(path, dirs):
    return any(path == d or path.startswith(d.rstrip("/") + "/") for d in dirs)


def _dedupe_roots(roots):
    """Drop duplicate or nested roots so no file is processed twice."""
    out = []
    for r in sorted({os.path.normpath(r) for r in roots}, key=len):
        if not _under(r, out):
            out.append(r)
    return out


_SERIAL = re.compile(r"\d{3,}|[0-9a-f]{8,}|^(img|dsc|frame|image|sample|screenshot|螢幕快照|截圖|スクリーンショット)", re.I)


def _serial(name: str) -> bool:
    """Machine-generated names like IMG_0001.jpg, frame_000123.png, 3f9a2c1e.json."""
    return bool(_SERIAL.search(os.path.splitext(name)[0]))


def name_text(path: str, is_dir: bool, note: str) -> str:
    p = Path(path)
    parents = [x for x in p.parent.parts[-3:] if x not in ("/", "Users")]
    kind = "folder" if is_dir else (p.suffix.lower().lstrip(".") or "file")
    s = f"{embed.readable_name(p.name) if not is_dir else p.name} ({kind})"
    s += " in " + " / ".join(parents)
    if note:
        s += f", contains {note}"
    return s


def app_names(paths):
    """Localized app names from Spotlight metadata, e.g. System Settings.app → 系統設定 on a Chinese system."""
    import subprocess
    out = {}
    for i in range(0, len(paths), 100):
        part = paths[i:i + 100]
        try:
            r = subprocess.run(["mdls", "-raw", "-name", "kMDItemDisplayName", *part],
                               capture_output=True, timeout=60)
            names = r.stdout.decode("utf-8", "ignore").split("\0")
        except Exception:
            continue
        for path, name in zip(part, names):
            name = name.strip()
            if name and name != "(null)":
                out[path] = name.removesuffix(".app")
    return out


def _extract_job(args):
    path, ext, size = args
    try:
        os.nice(10)
    except Exception:
        pass
    try:  # the file may have become cloud-only since it was scanned: never trigger a download
        if os.stat(path, follow_symlinks=False).st_flags & config.SF_DATALESS:
            return path, []
    except OSError:
        return path, []
    text = extract.extract(Path(path), ext, size)
    return path, extract.chunk(text) if text else []


EXTRACT_TIMEOUT = 300  # seconds allowed for extracting one batch of 100 documents


def _kill_pool(pool):
    for p in list(getattr(pool, "_processes", {}).values()):
        try:
            p.kill()
        except Exception:
            pass
    pool.shutdown(wait=False, cancel_futures=True)


def _extract_batch(pool, jobs, workers, on_progress=lambda: None):
    """Extract text in worker processes. If a file crashes or hangs a worker, restart the pool
    and treat that file as having no text."""
    from concurrent.futures import wait
    from concurrent.futures.process import BrokenProcessPool
    futs = {pool.submit(_extract_job, j): j[0] for j in jobs}
    done, not_done = wait(futs, timeout=EXTRACT_TIMEOUT)
    out, broken = {}, bool(not_done)
    for f in done:
        try:
            path, chunks = f.result()
            out[path] = chunks
        except BrokenProcessPool:
            broken = True
        except Exception:
            out[futs[f]] = []
    if broken:
        log("extractor hung or crashed; restarting the pool and retrying the rest one by one")
        _kill_pool(pool)
        pool = ProcessPoolExecutor(max_workers=workers)
        for path, ext, size in jobs:
            if path in out:
                continue
            f = pool.submit(_extract_job, (path, ext, size))
            on_progress()  # slow retries are still progress for the watchdog
            try:
                out[path] = f.result(timeout=60)[1]
            except Exception:
                log("  skipped:", path)
                out[path] = []
                _kill_pool(pool)
                pool = ProcessPoolExecutor(max_workers=workers)
    return out, pool


def _recently_used(days):
    """Paths Spotlight says were opened in the last `days` days, or None if mdfind failed."""
    import subprocess
    try:
        r = subprocess.run(["mdfind", f"kMDItemLastUsedDate >= $time.today(-{days})"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.splitlines() if r.returncode == 0 else None


def refresh_usage(db):
    """macOS remembers when each file was last opened. Four bucketed Spotlight queries
    (opened in the last 365 / 90 / 30 / 7 days) are enough; reading the attribute file by
    file would take minutes on a large index."""
    now = time.time()
    seen, ok = {}, False
    for days in (365, 90, 30, 7):  # oldest bucket first, so newer buckets overwrite
        paths = _recently_used(days)
        if paths is None:
            continue
        ok = True
        for p in paths:
            seen[p] = now - days * 86400 / 2  # middle of the bucket as an estimate
    if not ok:
        return  # keep the previous data rather than wiping it
    db.execute("DELETE FROM usage")
    db.executemany("INSERT OR REPLACE INTO usage VALUES(?, ?)", seen.items())
    log("recently used files:", len(seen))


OCR_BIN = Path(__file__).resolve().parent.parent / "bin" / "semsearch-ocr"
WAKE = config.DATA_DIR / "wake"  # created by the search service when new files show up
OCR_TIMEOUT = 90  # seconds allowed per file


def _ocr_size_ok(path):
    try:
        return os.path.getsize(path) <= config.OCR_MAX_BYTES
    except OSError:
        return False


def run_ocr(db, cfg, ctx, pending, flush, bump, progress, names_only):
    """Phase 3: recognize text in images and scanned PDFs with macOS Vision.

    Files in hot_roots (Downloads, Desktop) and newer files go first. Runs for at most
    `ocr_minutes` per index run and yields as soon as the service reports new files
    (the WAKE file); whatever is left is picked up by the next run.
    """
    import select
    import subprocess
    minutes = cfg.get("ocr_minutes", 15)
    if not OCR_BIN.exists() or not minutes or minutes <= 0:
        return
    if not db.execute("SELECT v FROM meta WHERE k='ocr_init'").fetchone():
        # OCR enabled for the first time: queue images already in the index and
        # PDFs that produced no text
        q = ",".join("?" * len(config.IMAGE_EXT))
        rows = db.execute(f"SELECT id, path FROM files WHERE dataless=0 AND is_dir=0 AND size <= ? "
                          f"AND ext IN ({q})", [config.OCR_MAX_BYTES, *config.IMAGE_EXT]).fetchall()
        rows += db.execute("SELECT id, path FROM files WHERE ext='.pdf' AND dataless=0 AND size <= ? "
                           "AND content_done=1 AND id NOT IN (SELECT file_id FROM chunks WHERE kind=1)",
                           (config.OCR_MAX_BYTES,)).fetchall()
        db.executemany("UPDATE files SET ocr_state=1 WHERE id=?",
                       [(fid,) for fid, path in rows if not _under(path, names_only)])
        db.execute("INSERT OR REPLACE INTO meta VALUES('ocr_init', '1')")
        db.commit()
    rows = db.execute("SELECT id, path, name, mtime FROM files WHERE ocr_state=1 AND dataless=0").fetchall()
    if not rows:
        return
    hot = cfg["hot_roots"]
    rows.sort(key=lambda r: (not _under(r[1], hot), -(r[3] or 0)))
    log("files waiting for OCR:", len(rows))
    deadline = time.time() + minutes * 60
    proc = None
    done = found = 0
    t0 = time.time()

    def start():
        # taskpolicy -b: lowest macOS background priority, so OCR never slows the Mac down
        return subprocess.Popen(["taskpolicy", "-b", str(OCR_BIN)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, text=True, bufsize=1)
    try:
        for fid, path, name, _ in rows:
            if time.time() > deadline:
                break
            if WAKE.exists():  # new files are waiting: step aside, OCR resumes next run
                log("new files detected; pausing OCR")
                break
            if proc is None or proc.poll() is not None:
                proc = start()
            text = ""
            try:
                proc.stdin.write(path + "\n")
                proc.stdin.flush()
                ready, _, _ = select.select([proc.stdout], [], [], OCR_TIMEOUT)
                if ready:
                    line = proc.stdout.readline()
                    if line:
                        text = json.loads(line).get("text", "")
                else:  # stuck: start a fresh helper and skip this file
                    proc.kill()
                    proc = None
            except (OSError, ValueError):
                proc = None
            text = extract._clean(text)
            if len(text) >= 20 and not extract.garbled(text):
                ctx[fid] = embed.readable_name(name)
                old = [r[0] for r in db.execute("SELECT id FROM chunks WHERE file_id=? AND kind=1", (fid,))]
                if old:
                    qm = ",".join("?" * len(old))
                    db.execute(f"DELETE FROM chunks_fts WHERE rowid IN ({qm})", old)
                    db.execute(f"DELETE FROM chunks WHERE id IN ({qm})", old)
                for c in extract.chunk(text[: config.MAX_CHARS_PER_FILE]):
                    pending.append((fid, KIND_CONTENT, c))
                found += 1
            db.execute("UPDATE files SET ocr_state=2 WHERE id=?", (fid,))
            done += 1
            progress[0] = time.time()
            if len(pending) >= 256 or done % 50 == 0:
                flush()
                bump()
                log(f"  OCR {done}/{len(rows)} ({(time.time() - t0) / done:.2f} s each, {found} with text)")
        flush()
        bump()
    finally:
        if proc and proc.poll() is None:
            proc.stdin.close()
            proc.kill()
    log(f"OCR: {done} files, {found} with text, {time.time() - t0:.0f}s, {len(rows) - done} left")


def run(full=False, limit=None, workers=4, quick=False):
    cfg = config.load()
    WAKE.unlink(missing_ok=True)  # this run picks up the new files
    _exclude_substrings[:] = cfg.get("exclude_substrings", [])
    embed.get_model(cfg["model"])
    db = connect()
    old_model = db.execute("SELECT v FROM meta WHERE k='model'").fetchone()
    if full or (old_model and old_model[0] != cfg["model"]):
        log("clearing the old index")
        db.executescript("DELETE FROM files; DELETE FROM chunks; DELETE FROM chunks_fts;")
    db.execute("INSERT OR REPLACE INTO meta VALUES('model', ?)", (cfg["model"],))
    # Unique and increasing even when two runs start within the same second
    last = db.execute("SELECT max(seen) FROM files").fetchone()[0] or 0
    scan_id = max(int(time.time() * 1000), last + 1)
    known = {r[0]: (r[1], r[2], r[3], r[4])
             for r in db.execute("SELECT path, id, size, mtime, dataless FROM files")}
    log("known entries:", len(known))

    todo = []  # (path, st, is_dir, note, dataless)
    unchanged = []
    n = 0
    last_full = db.execute("SELECT v FROM meta WHERE k='last_full'").fetchone()
    if quick and (not last_full or time.time() - float(last_full[0]) > config.FULL_EVERY):
        log("last full scan is over 6 hours old; doing a full scan")
        quick = False
    roots = _dedupe_roots([r for r in cfg["roots"] if not quick or r in cfg["hot_roots"]])
    failed = []
    progress = [time.time()]

    # Watchdog: the MPS backend occasionally hangs, and so can reading a folder (cloud
    # provider, permission prompt). With no progress for 15 minutes, exit; finished batches
    # are committed and the next scheduled run resumes from there.
    def watchdog():
        while True:
            time.sleep(60)
            if time.time() - progress[0] > 900:
                log("no progress for 15 minutes; exiting so the next run can resume")
                os._exit(3)
    import threading
    threading.Thread(target=watchdog, daemon=True).start()

    for path, st, is_dir, note in walk(roots, failed):
        n += 1
        dataless = int(bool(getattr(st, "st_flags", 0) & config.SF_DATALESS))
        k = known.get(path)
        size = 0 if is_dir else st.st_size
        if k and k[1] == size and abs(k[2] - st.st_mtime) < 1 and k[3] == dataless and not is_dir:
            unchanged.append(k[0])
        elif k and is_dir and abs(k[2] - st.st_mtime) < 1:
            unchanged.append(k[0])
        else:
            todo.append((path, st, is_dir, note, dataless))
        if limit and len(todo) >= limit:
            break
        if n % 1000 == 0:
            progress[0] = time.time()
        if n % 50000 == 0:
            log("scanning", n)
    log(f"scanned {n} entries: {len(todo)} to update, {len(unchanged)} unchanged")
    for i in range(0, len(unchanged), 5000):
        ids = unchanged[i:i + 5000]
        db.execute(f"UPDATE files SET seen=? WHERE id IN ({','.join('?' * len(ids))})",
                   [scan_id, *ids])
    db.commit()

    pending = []  # (file_id, kind, text)
    ctx = {}  # file_id -> readable file name

    def flush():
        if not pending:
            return
        vecs = embed.encode([f"{ctx[f]}: {t}" if k == KIND_CONTENT else t for f, k, t in pending])
        for (fid, kind, text), v in zip(pending, vecs):
            cur = db.execute("INSERT INTO chunks(file_id, kind, text, vec) VALUES(?,?,?,?)",
                             (fid, kind, text, v.tobytes()))
            db.execute("INSERT INTO chunks_fts(rowid, text) VALUES(?,?)", (cur.lastrowid, text))
        pending.clear()
        progress[0] = time.time()

    def drop_chunks(fid, content_only=False):
        sql = "SELECT id FROM chunks WHERE file_id=?" + (" AND kind=1" if content_only else "")
        old = [r[0] for r in db.execute(sql, (fid,))]
        if old:
            q = ",".join("?" * len(old))
            db.execute(f"DELETE FROM chunks_fts WHERE rowid IN ({q})", old)
            db.execute(f"DELETE FROM chunks WHERE id IN ({q})", old)

    def bump():
        db.execute("INSERT OR REPLACE INTO meta VALUES('version', ?)", (str(time.time()),))
        db.commit()

    names_only = cfg["names_only_roots"]
    apps = app_names([t[0] for t in todo if t[0].endswith(".app")])
    # Phase 1: embed every name first (fast), so the whole index is searchable by name right away
    t0 = time.time()
    batch = 2000
    for b in range(0, len(todo), batch):
        part = todo[b:b + batch]
        for path, st, is_dir, note, dataless in part:
            p = Path(path)
            k = known.get(path)
            if k:
                drop_chunks(k[0])
                db.execute("DELETE FROM files WHERE id=?", (k[0],))
            ext = p.suffix.lower()
            wants_content = (not is_dir and not dataless and ext in config.CONTENT_EXT
                             and not any(path.startswith(r.rstrip("/") + "/") for r in names_only))
            name = p.name
            local = apps.get(path)
            if local and local != p.stem:
                name = f"{local}（{p.name}）"  # localized name first so keyword matching finds it too
            wants_ocr = (not is_dir and not dataless and ext in config.IMAGE_EXT
                         and st.st_size <= config.OCR_MAX_BYTES and not _under(path, names_only))
            cur = db.execute(
                "INSERT INTO files(path,name,parent,ext,size,mtime,is_dir,dataless,note,seen,"
                "content_done,ocr_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (path, name, str(p.parent), ext, 0 if is_dir else st.st_size,
                 st.st_mtime, int(is_dir), dataless, note, scan_id, 0 if wants_content else 1,
                 1 if wants_ocr else 0))
            text = name_text(path, is_dir, note)
            if local:
                text = f"{local} (app / 應用程式) " + text
            pending.append((cur.lastrowid, KIND_NAME, text))
            if len(pending) >= 512:
                flush()
        flush()
        bump()
        done = b + len(part)
        log(f"  names {done}/{len(todo)} ({done / (time.time() - t0):.0f}/s)")

    # Apps: index a one-line "what it is for" description as the app's text, so a query like
    # "note-taking app" or "take a screenshot" finds it. Covers apps indexed before this existed.
    rows = db.execute("SELECT id, path, name FROM files WHERE ext='.app' AND id NOT IN "
                      "(SELECT file_id FROM chunks WHERE kind=1)").fetchall()
    for fid, path, name in rows:
        desc = appinfo.describe(path)
        if desc:
            ctx[fid] = embed.readable_name(name)
            pending.append((fid, KIND_CONTENT, desc))
    flush()
    if rows:
        bump()
        log("app descriptions", len(rows))

    # Phase 2: document contents, including leftovers from an interrupted run.
    # At most 3 attempts per document, so one broken PDF can't block every future run.
    rows = db.execute("SELECT id, path, ext, size, name FROM files "
                      "WHERE content_done=0 AND content_tries < 3 AND dataless=0").fetchall()
    log("documents to read:", len(rows))
    t1 = time.time()
    batch = 100
    pool = ProcessPoolExecutor(max_workers=workers)
    try:
        for b in range(0, len(rows), batch):
            part = rows[b:b + batch]
            db.executemany("UPDATE files SET content_tries = content_tries + 1 WHERE id=?",
                           [(r[0],) for r in part])
            db.commit()
            contents, pool = _extract_batch(pool, [(path, ext, size) for _, path, ext, size, _ in part],
                                            workers, on_progress=lambda: progress.__setitem__(0, time.time()))
            for fid, path, ext, size, name in part:
                drop_chunks(fid, content_only=True)
                ctx[fid] = embed.readable_name(name)
                for c in contents.get(path, []):
                    pending.append((fid, KIND_CONTENT, c))
                if len(pending) >= 512:
                    flush()
            flush()
            db.executemany("UPDATE files SET content_done=1 WHERE id=?", [(r[0],) for r in part])
            # A PDF without extractable text is most likely a scan: queue it for OCR
            db.executemany("UPDATE files SET ocr_state=1 WHERE id=?",
                           [(fid,) for fid, path, ext, _, _ in part
                            if ext == ".pdf" and not contents.get(path) and _ocr_size_ok(path)])
            bump()
            progress[0] = time.time()  # a batch with no extractable text (scanned PDFs) is still progress
            done = b + len(part)
            el = time.time() - t1
            log(f"  contents {done}/{len(rows)} ({done / el:.1f}/s, ~{(len(rows) - done) * el / done / 60:.0f} min left)")
    finally:
        _kill_pool(pool)

    refresh_usage(db)
    db.commit()
    # Phase 3: OCR of images and scanned PDFs, at most `ocr_minutes` per run
    if not limit:
        run_ocr(db, cfg, ctx, pending, flush, bump, progress, names_only)

    if not limit:
        # Remove entries that vanished, but only under roots scanned this time and never
        # under folders that could not be read (maybe just a temporary permission/cloud error)
        ok_roots = [r for r in roots if r not in failed]
        if failed:
            log(f"{len(failed)} folders could not be read; keeping their entries:", ", ".join(failed[:5]))
        gone = [fid for fid, path in db.execute("SELECT id, path FROM files WHERE seen != ?", (scan_id,))
                if _under(path, ok_roots) and not _under(path, failed)]
        for i in range(0, len(gone), 2000):
            ids = gone[i:i + 2000]
            q = ",".join("?" * len(ids))
            cids = [r[0] for r in db.execute(f"SELECT id FROM chunks WHERE file_id IN ({q})", ids)]
            for j in range(0, len(cids), 2000):
                cq = ",".join("?" * len(cids[j:j + 2000]))
                db.execute(f"DELETE FROM chunks_fts WHERE rowid IN ({cq})", cids[j:j + 2000])
                db.execute(f"DELETE FROM chunks WHERE id IN ({cq})", cids[j:j + 2000])
            db.execute(f"DELETE FROM files WHERE id IN ({q})", ids)
        log("removed vanished entries:", len(gone))
    db.execute("INSERT OR REPLACE INTO meta VALUES('version', ?)", (str(time.time()),))
    db.execute("INSERT OR REPLACE INTO meta VALUES('last_index', ?)", (time.strftime("%Y-%m-%d %H:%M"),))
    if not quick and not limit:
        db.execute("INSERT OR REPLACE INTO meta VALUES('last_full', ?)", (str(time.time()),))
    db.commit()
    nf = db.execute("SELECT count(*) FROM files").fetchone()[0]
    nc = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
    log(f"done: {nf} files/folders, {nc} vectors, {time.time() - t0:.0f}s")
    db.close()


def main():
    # Debugging: `kill -USR1 <pid>` writes every thread's current stack to indexer.log
    import faulthandler
    import signal
    faulthandler.register(signal.SIGUSR1, all_threads=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="rebuild from scratch")
    ap.add_argument("--limit", type=int, help="process only the first N entries (testing)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--quick", action="store_true", help="scan only hot_roots (Downloads, Desktop)")
    a = ap.parse_args()
    lock = config.DATA_DIR / "indexer.lock"
    config.DATA_DIR.mkdir(exist_ok=True)
    import fcntl
    fh = open(lock, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another indexer is running; skipping")
        sys.exit(0)
    run(full=a.full, limit=a.limit, workers=a.workers, quick=a.quick)


if __name__ == "__main__":
    main()
