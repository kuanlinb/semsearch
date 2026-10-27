"""Hybrid search: semantic vectors + keywords (names and contents), fused with RRF.

All vectors live in memory (a float16 tensor on MPS, or a float16 NumPy array without
PyTorch); a few hundred thousand chunks take tens of milliseconds. The service reloads
them after the indexer updates the DB.
"""
import os
import re
import sqlite3
import threading
import time

import numpy as np

from . import conditions, config, embed, extract, usage

# Usage boost: files opened within USAGE_DAYS move up (more the more recent), and so do
# files opened from the search panel, especially for the same query
USAGE_DAYS = 90
W_RECENT, W_OPENS, W_SAME_QUERY = 0.15, 0.3, 0.6
REMOTE_TIMEOUT = 3     # seconds to wait for a remote reranker
REMOTE_BACKOFF = 15    # after a failure, don't try the remote reranker again for this long
REMOTE_PROBE = 0.5     # seconds a health check may take; searches use the remote only after one passes
REMOTE_PROBE_EVERY = 5  # while it is down, check again this often (in the background, not in a search)
RRF_K = 20  # tuned with eval/tune.py
W_NAME, W_CONTENT = 1.0, 1.0
# Also count how far ahead a file's content similarity is, so a clear content match is not
# cancelled out by unhelpful file names ("Document (3).txt"). Tuned on two query sets.
# Results come in two tiers and weak ones are dropped, but only with reranker scores: vector
# similarity alone cannot tell relevant from irrelevant. Only the distance from the top score
# counts, never the raw score: the same model gives a correct but indirect match as little as
# -6.7 ("flight to osaka" for a TPE-KIX booking) while a question with no answer can top at -0.2.
# Checked with bge-reranker-v2-m3 on 50 real queries, 28 demo queries in four languages and 76
# hard ones with look-alike files: every correct file stays visible. The margin is thin: correct
# files sat 4.7 below the top and as low as -9.6 ("單一登入誰負責" for English meeting notes), so
# tighter values (4.5 / -7.5) hid answers. Other rerankers score on another scale.
# Ranked list truncation by the gap from the top score (Arampatzis 2009; Meng 2024).
# Files the reranker did not see are judged by their fast-search rank instead: with rerank_top
# below TIER_SPAN, the unseen files up to rank TIER_SPAN stay in the second tier (a correct file
# ranked 21-40 would otherwise vanish unjudged), the rest are dropped.
TIER_SPAN = 40
TIER1_GAP = 2.0                       # first tier: within 2 of the top score (reranker logits)
SHOW_GAP, SHOW_FLOOR = 5.0, -10.0     # second tier ("less related"); further or below -10 (unrelated) is hidden
W_SIM = 0.4
SENT_CHARS = 160  # the answer-sentence step embeds at most this much of each sentence
# Codes, IDs and long numbers ("58210377", "NT$18,600", "MXV-2291") mean nothing to an embedding,
# so for such lookups the keyword match counts more and the vector lists less. Measured on
# eval/lookalike: those lookups went from rank 13-20 to first, nothing else moved.
LOOKUP_KW, LOOKUP_VEC = 3.0, 0.5
# Optional image list (config "image_search", semsearch/imagevec.py): photos ranked by how well
# what they show matches the query. Every photo scores something (unrelated ones about 0.6), so
# only those near the top score and above a floor count. Prototype values; env overrides for tuning.
W_IMAGE = float(os.environ.get("SEMSEARCH_W_IMAGE", 1.0))
IMAGE_GAP = float(os.environ.get("SEMSEARCH_IMAGE_GAP", 0.05))
IMAGE_FLOOR = float(os.environ.get("SEMSEARCH_IMAGE_FLOOR", 0.0))
IMAGE_TOP = 10
IMAGE_Z = float(os.environ.get("SEMSEARCH_IMAGE_Z", 0.0))  # the best image must stand out this much
# When the text model is the same EmbeddingGemma ("shared" space), images compete with content
# chunks on raw similarity instead; image-to-text similarities run lower than text-to-text
# (modality gap), so they get IMAGE_OFFSET added.
IMAGE_OFFSET = float(os.environ.get("SEMSEARCH_IMAGE_OFFSET", 0.0))
# "gemma_channel": next to the main model's lists, one more list from EmbeddingGemma vectors of the
# same chunks, with the images ranked in it (same space). Its weight:
W_GEMMA = float(os.environ.get("SEMSEARCH_W_GEMMA", 1.0))
# An image has no main-model vectors and no keywords, so its rank in the Gemma list stands in for
# the lists it is missing: counted IMAGE_MULT times, but only when it beats every text chunk in the
# Gemma space (similarity + IMAGE_OFFSET); otherwise photos would push documents down for text questions
IMAGE_MULT = float(os.environ.get("SEMSEARCH_IMAGE_MULT", 6.0))  # eval/embeddinggemma2: 6 with offset 0


# Filler words in English queries are not matched as keywords ("our" would hit "sourdough")
STOPWORDS = {"a", "an", "the", "my", "our", "your", "his", "her", "their", "is", "are", "was", "were",
             "be", "of", "to", "for", "in", "on", "at", "by", "and", "or", "how", "much", "many", "what",
             "when", "where", "which", "who", "why", "do", "does", "did", "i", "me", "we", "us", "you",
             "it", "that", "this", "these", "those", "with", "from", "about", "can", "should", "need"}


def _terms(q: str):
    terms = [t for t in re.split(r"\s+", q.strip()) if t]
    if len(terms) > 1:
        kept = [t for t in terms if t.lower() not in STOPWORDS]
        return kept or terms
    return terms


_SLIDES = {".pptx", ".ppt", ".key", ".pdf"}
_SHEET = {".xlsx", ".xls", ".csv", ".numbers"}
_IMAGE = {".png", ".jpg", ".jpeg", ".heic", ".gif", ".webp"}
_VIDEO = {".mp4", ".mov", ".mkv", ".avi"}
_AUDIO = {".m4a", ".mp3", ".wav", ".aac"}
# File-type words in a query express a preference for that type; they are not
# matched against file names.
TYPE_WORDS = [
    ("pdf", {".pdf"}), ("ppt", {".pptx", ".ppt"}), ("slides", _SLIDES), ("簡報", _SLIDES),
    ("投影片", _SLIDES), ("word", {".docx", ".doc"}), ("excel", _SHEET), ("spreadsheet", _SHEET),
    ("試算表", _SHEET), ("表格", _SHEET), ("image", _IMAGE), ("picture", _IMAGE), ("圖片", _IMAGE),
    ("照片", _IMAGE), ("screenshot", {".png", ".jpg"}), ("截圖", {".png", ".jpg"}),
    ("video", _VIDEO), ("影片", _VIDEO), ("錄影", _VIDEO), ("audio", _AUDIO), ("recording", _AUDIO),
    ("錄音", _AUDIO), ("音檔", _AUDIO), ("notebook", {".ipynb"}), ("zip", {".zip", ".rar", ".7z"}),
    ("壓縮檔", {".zip", ".rar", ".7z"}), ("folder", {"<dir>"}), ("資料夾", {"<dir>"}),
    ("app", {".app"}), ("應用程式", {".app"}),
    # Simplified Chinese, Japanese, Korean
    ("幻灯片", _SLIDES), ("电子表格", _SHEET), ("图片", _IMAGE), ("截图", {".png", ".jpg"}), ("视频", _VIDEO),
    ("录音", _AUDIO), ("压缩包", {".zip", ".rar", ".7z"}), ("文件夹", {"<dir>"}), ("应用", {".app"}),
    ("スライド", _SLIDES), ("スプレッドシート", _SHEET), ("画像", _IMAGE), ("写真", _IMAGE),
    ("スクリーンショット", {".png", ".jpg"}), ("動画", _VIDEO), ("録音", _AUDIO), ("フォルダ", {"<dir>"}),
    ("アプリ", {".app"}), ("슬라이드", _SLIDES), ("스프레드시트", _SHEET), ("이미지", _IMAGE), ("사진", _IMAGE),
    ("스크린샷", {".png", ".jpg"}), ("동영상", _VIDEO), ("녹음", _AUDIO), ("폴더", {"<dir>"}), ("앱", {".app"}),
]

_H = os.path.expanduser("~")
_TR = config.translations(config.ui_language())
# Common places, shown first when the query is (essentially) their name.
# strong=True (Trash) also matches when the word merely appears in the query.
# (name, path, aliases in any language, strong, description); name and description are shown translated
_PLACES = [
    ("Trash", f"{_H}/.Trash", ["trash", "bin", "垃圾桶", "垃圾筒", "資源回收筒", "回收筒", "废纸篓", "ゴミ箱", "휴지통"],
     True, "Finder Trash, press ↩ to open"),
    ("Applications", "/Applications", ["applications", "app", "應用程式", "应用程序", "アプリケーション", "응용프로그램"],
     False, "All apps"),
    ("Downloads", f"{_H}/Downloads", ["downloads", "下載", "下载", "ダウンロード", "다운로드"], False, "Folder"),
    ("Desktop", f"{_H}/Desktop", ["desktop", "桌面", "デスクトップ", "데스크탑", "바탕화면"], False, "Folder"),
    ("Documents", f"{_H}/Documents", ["documents", "文件", "文稿", "書類", "문서"], False, "Folder"),
    ("Pictures", f"{_H}/Pictures", ["pictures", "圖片", "图片", "ピクチャ", "사진"], False, "Folder"),
    ("Movies", f"{_H}/Movies", ["movies", "影片", "ムービー", "동영상"], False, "Folder"),
    ("Music", f"{_H}/Music", ["music", "音樂", "音乐", "ミュージック", "음악"], False, "Folder"),
    ("Home", _H, ["home", "家目錄", "個人專屬", "个人文件夹", "ホーム", "홈"], False, "Your home folder"),
]
for _d in config.cloud_drives():
    _n = os.path.basename(_d)
    _n = "iCloud Drive" if _n == "com~apple~CloudDocs" else _n
    _PLACES.append((_n, _d, [_n.lower(), _n.split("-")[0].lower()], False, "Cloud drive"))


def _contains_word(text, word):
    """English words must stand alone ("bin" ≠ "binary"); CJK words match as substrings."""
    if word.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text) is not None
    return word in text


def match_places(q: str):
    norm = re.sub(r"(打開|開啟|打开|資料夾|文件夹|フォルダ|폴더|folder|open|my|the|的|在哪|\s)+", "", q.lower())
    out = []
    for name, path, aliases, strong, desc in _PLACES:
        if any(norm == a.replace(" ", "") or (strong and _contains_word(q.lower(), a)) for a in aliases):
            out.append({"path": path, "name": _TR.get(name, name), "ext": "", "size": 0, "mtime": 0,
                        "is_dir": True, "cloud": False, "note": "", "match": "place",
                        "snippet": _TR.get(desc, desc), "score": 999, "semantic": 1.0,
                        "copies": 0})
    return out


def parse_types(q: str):
    """Return (query without type words, wanted extensions or None)."""
    low, want = q.lower(), set()
    for word, exts in TYPE_WORDS:
        pat = rf"(?<![a-z0-9]){word}(?![a-z0-9])" if word.isascii() else re.escape(word)
        if re.search(pat, low):
            want |= exts
            low = re.sub(pat, " ", low)
    return (re.sub(r"\s+", " ", low).strip() or q.lower()), (want or None)


def _code_like(term: str) -> bool:
    """A number or an ID: has digits, no CJK, and is long enough not to be a version like "Q3"."""
    digits = sum(c.isdigit() for c in term)
    return digits > 0 and term.isascii() and (digits >= 3 or len(term) >= 4)


def is_lookup(q: str) -> bool:
    """Every word of the query is a code or a number ("58210377", "Q7XK2P", "B2-17")."""
    terms = _terms(q)
    return bool(terms) and all(_code_like(t) for t in terms)


_pool = None


def _scores(mat, qv, block=8192):
    """mat @ qv for a float16 matrix without PyTorch. NumPy has no fast float16 matmul, so
    blocks are converted to float32 and multiplied on several threads (NumPy releases the GIL)."""
    global _pool
    if _pool is None:
        from concurrent.futures import ThreadPoolExecutor
        _pool = ThreadPoolExecutor(max(1, min(8, (os.cpu_count() or 4) - 2)))
    q = qv.astype(np.float32)
    if len(mat) <= block:
        return mat.astype(np.float32) @ q
    return np.concatenate(list(_pool.map(lambda i: mat[i:i + block].astype(np.float32) @ q,
                                         range(0, len(mat), block))))


class Searcher:
    def __init__(self):
        self.cfg = config.load()
        embed.get_model(self.cfg["model"])
        self._qcache = {}
        self.reranker = None
        if self.cfg.get("onnx_reranker"):  # a local int8 export: no PyTorch, CPU only
            self.reranker = embed.OnnxReranker(self.cfg["onnx_reranker"])
        elif self.cfg.get("reranker"):
            try:
                from sentence_transformers import CrossEncoder
            except ImportError:  # the light install has no PyTorch: install.sh adds it for a reranker
                print("reranker needs PyTorch: run install.sh again to add it", flush=True)
            else:
                dev = config.device()
                self.reranker = CrossEncoder(self.cfg["reranker"], device=dev, max_length=256)
                if dev == "mps":
                    self.reranker.model.half()
        self.remote = self.cfg.get("remote_reranker", "")
        self.remote_ok, self.remote_down_until = False, 0.0
        if self.remote:
            # Check now and keep checking in the background, so a search never waits on a link that
            # is not up yet (the SSH tunnel after login or wake) or has gone away
            self._remote_probe()
            threading.Thread(target=self._remote_watch, daemon=True).start()
        self.recent = {}
        self.lock = threading.Lock()
        self.gpu = threading.Lock()  # PyTorch MPS is not thread-safe: one GPU op at a time
        self.torch = config.embed_backend() == "torch"
        self.version = None
        self.mat = None
        self.chunk_ids = None
        self.chunk_file = None
        self.reload(force=True)

    def _db(self):
        db = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True, timeout=30)
        return db

    def current_version(self):
        try:
            db = self._db()
            r = db.execute("SELECT v FROM meta WHERE k='version'").fetchone()
            db.close()
            return r[0] if r else None
        except sqlite3.Error:
            return None

    def reload(self, force=False):
        v = self.current_version()
        if not force and v == self.version:
            return False
        db = self._db()
        model = db.execute("SELECT v FROM meta WHERE k='model'").fetchone()
        rows = db.execute("SELECT id, file_id, kind, vec FROM chunks").fetchall()
        db.close()
        if model and model[0] != embed._name:
            # The index was rebuilt with another model; queries must use the same one
            with self.gpu:
                embed.reset()
                embed.get_model(model[0])
        if rows:
            ids = np.fromiter((r[0] for r in rows), dtype=np.int64, count=len(rows))
            fids = np.fromiter((r[1] for r in rows), dtype=np.int64, count=len(rows))
            kinds = np.fromiter((r[2] for r in rows), dtype=np.int8, count=len(rows))
            vecs = np.frombuffer(b"".join(r[3] for r in rows), dtype=np.float16).reshape(len(rows), -1)
            if self.torch:
                import torch
                dev = config.device()
                cpu = torch.from_numpy(vecs.copy())
                with self.gpu:
                    mat = cpu.to(dev)
                if dev == "cpu":
                    mat = mat.float()
            else:
                mat = vecs.copy()  # stays float16; _scores converts one block at a time
        else:
            ids = fids = np.zeros(0, dtype=np.int64)
            kinds = np.zeros(0, dtype=np.int8)
            mat = None
        g_fids, g_mat = np.zeros(0, dtype=np.int64), None
        if self.cfg.get("gemma_channel"):
            db = self._db()
            try:
                g = db.execute("SELECT c.file_id, g.vec FROM gemma_vecs g JOIN chunks c ON c.id = g.chunk_id").fetchall()
            except sqlite3.Error:
                g = []
            db.close()
            if g:
                g_fids = np.fromiter((r[0] for r in g), dtype=np.int64, count=len(g))
                g_mat = np.frombuffer(b"".join(r[1] for r in g), dtype=np.float16).reshape(len(g), -1).copy()
        img_ids, img_mat = np.zeros(0, dtype=np.int64), None
        if self.cfg.get("image_search"):
            db = self._db()
            try:
                img = [(f, v) for f, v in db.execute("SELECT file_id, vec FROM image_vecs") if v]
            except sqlite3.Error:
                img = []
            db.close()
            if img:
                img_ids = np.array([f for f, _ in img], dtype=np.int64)
                img_mat = np.frombuffer(b"".join(v for _, v in img), dtype=np.float16).reshape(len(img), -1)
                img_mat = img_mat.astype(np.float32)
        db = self._db()
        try:
            recent = dict(db.execute("SELECT f.id, u.last_used FROM usage u JOIN files f ON f.path = u.path"))
        except sqlite3.Error:  # index created by an older version
            recent = {}
        db.close()
        names = _NameIndex(self._db())
        app_ids = {f for f, (ext, _) in names.kind.items() if ext == ".app"}
        # an app's name and its "what it is for" description both count
        app_rows = np.array([i for i in range(len(fids)) if int(fids[i]) in app_ids], dtype=np.int64)
        with self.lock:
            self.app_rows = app_rows
            self.mat, self.chunk_ids, self.chunk_file, self.version = mat, ids, fids, v
            self.chunk_kind = kinds
            self.img_ids, self.img_mat = img_ids, img_mat
            self.g_fids, self.g_mat = g_fids, g_mat
            self.names = names
            self.recent = recent
        return True

    def maybe_reload(self, min_interval=0):
        if time.time() - getattr(self, "last_reload", 0) < min_interval:
            return
        try:
            if self.reload():
                self.last_reload = time.time()
        except Exception as e:  # a half-written index must not break search
            print("reload failed", e, flush=True)

    def _rerank(self, db, q, order, best_chunk, kw):
        """Re-rank the top results with a cross-encoder that reads query and document together."""
        top = order[: self.cfg.get("rerank_top", 40)]
        texts = []
        for fid in top:
            name = db.execute("SELECT text FROM chunks WHERE file_id=? AND kind=0", (fid,)).fetchone()
            cid = best_chunk.get(fid)
            body = None
            if cid:
                body = db.execute("SELECT text FROM chunks WHERE id=?", (cid,)).fetchone()
            if not body:
                body = db.execute("SELECT text FROM chunks WHERE file_id=? AND kind=1 ORDER BY id LIMIT 1",
                                  (fid,)).fetchone()
            texts.append(((name[0] if name else "") + "\n" + (body[0][:400] if body else "")).strip())
        scores = self._remote_scores(q, texts) if self.remote else None
        if scores is None and isinstance(self.reranker, embed.OnnxReranker):
            scores = self.reranker.scores(q, texts)
        elif scores is None and self.reranker:
            with self.gpu:
                import torch
                # raw logits, the same scale as the remote reranker (the tier thresholds use it)
                scores = self.reranker.predict([(q, t) for t in texts], batch_size=16, show_progress_bar=False,
                                               activation_fn=torch.nn.Identity())
        if scores is None or len(scores) != len(top):
            return order, False, {}  # no reranker reachable: keep the fast order
        bonus = {fid: (1.0 if fid in kw and kw[fid][2] else 0.0) for fid in top}
        ranked = sorted(zip(top, scores), key=lambda x: -(float(x[1]) + bonus[x[0]]))
        return [f for f, _ in ranked] + order[len(top):], True, {f: float(sc) for f, sc in zip(top, scores)}

    def _remote_probe(self):
        """Whether the remote reranker answers at all (any HTTP reply counts); searches use it only then."""
        import urllib.error
        import urllib.request
        try:
            urllib.request.urlopen(self.remote.rstrip("/") + "/health", timeout=REMOTE_PROBE).close()
            self.remote_ok = True
        except urllib.error.HTTPError:
            self.remote_ok = True
        except Exception:
            self.remote_ok = False

    def _remote_watch(self):
        while True:
            time.sleep(REMOTE_PROBE_EVERY)
            if not self.remote_ok and time.time() >= self.remote_down_until:
                self._remote_probe()

    def _remote_scores(self, q, texts):
        """Scores from the remote reranker (remote/rerank_server.py), or None when it is down;
        after a failure it is not tried again for REMOTE_BACKOFF seconds, then only once a
        background health check passes."""
        import json
        import urllib.request
        if not self.remote_ok:
            return None
        try:
            req = urllib.request.Request(self.remote.rstrip("/") + "/rerank",
                                         data=json.dumps({"query": q, "texts": texts}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=REMOTE_TIMEOUT) as r:
                return [float(x) for x in json.load(r)["scores"]]
        except Exception as e:
            print("remote rerank failed:", repr(e), flush=True)
            self.remote_ok, self.remote_down_until = False, time.time() + REMOTE_BACKOFF
            return None

    # ---- retrieval channels ----
    def _vector(self, q, k=2500, allow=None):
        """Return [(chunk id, file id, kind, score)], best first. allow: file ids to keep (conditions)."""
        with self.lock:
            mat, ids, fids, kinds = self.mat, self.chunk_ids, self.chunk_file, self.chunk_kind
        if mat is None:
            return []
        keep = None if allow is None else np.isin(fids, allow)
        if self.torch:
            import torch
            with self.gpu:
                qv = torch.from_numpy(self._qvec(q)).to(mat.device).to(mat.dtype)
                if qv.shape[1] != mat.shape[1]:
                    raise RuntimeError("index and query model differ; wait for the rebuild to finish")
                scores = (mat @ qv[0]).float()
                if keep is not None:
                    scores[torch.from_numpy(~keep).to(scores.device)] = -10.0
                k = min(k, scores.shape[0])
                top = torch.topk(scores, k)
                s = top.values.cpu().numpy()
                idx = top.indices.cpu().numpy()
        else:
            qv = self._qvec(q)
            if qv.shape[1] != mat.shape[1]:
                raise RuntimeError("index and query model differ; wait for the rebuild to finish")
            scores = _scores(mat, qv[0])
            if keep is not None:
                scores[~keep] = -10.0
            k = min(k, len(scores))
            idx = np.argpartition(-scores, k - 1)[:k]
            idx = idx[np.argsort(-scores[idx], kind="stable")]
            s = scores[idx]
        return [(int(ids[i]), int(fids[i]), int(kinds[i]), float(sc)) for i, sc in zip(idx, s) if sc > -10.0]

    def _usage_boost(self, fused, q):
        """Move frequently used files up: recently opened (Spotlight's last-used date), often
        opened from the search panel, or opened before for the same query."""
        now = time.time()
        for fid, last in self.recent.items():
            if fid in fused:
                days = (now - last) / 86400
                if days < USAGE_DAYS:
                    fused[fid] *= 1 + W_RECENT * (1 - days / USAGE_DAYS)
        opens = usage.load()
        if not opens:
            return
        ids = self._ids_for(list(opens))
        qn = usage.norm(q)
        for path, (count, queries) in opens.items():
            fid = ids.get(path)
            if fid in fused:
                fused[fid] *= 1 + W_OPENS * min(count, 5) / 5 + (W_SAME_QUERY if qn in queries else 0)

    def _ids_for(self, paths):
        db = self._db()
        out = {}
        for i in range(0, len(paths), 500):
            part = paths[i:i + 500]
            out.update(db.execute(f"SELECT path, id FROM files WHERE path IN ({','.join('?' * len(part))})", part))
        db.close()
        return out

    def _app_vector(self, q):
        """All apps ranked by how well their name or description matches the query; returns file ids."""
        with self.lock:
            mat, fids, rows = self.mat, self.chunk_file, self.app_rows
        if mat is None or rows is None or len(rows) == 0:
            return []
        if self.torch:
            import torch
            with self.gpu:
                qv = torch.from_numpy(self._qvec(q)).to(mat.device).to(mat.dtype)
                sc = (mat[torch.as_tensor(rows, device=mat.device)] @ qv[0]).float().cpu().numpy()
        else:
            sc = _scores(mat[rows], self._qvec(q)[0])
        best = {}
        for i in np.argsort(-sc):
            best.setdefault(int(fids[rows[i]]), None)
        return list(best)

    def _keyword(self, db, q, k=200):
        """Return {file_id: (score, matching chunk id or None, every term in the name)}."""
        terms = _terms(q)
        if not terms:
            return {}
        hits = {}
        # Names: any term counts, all terms rank first; for one-term queries folder paths count too
        for fid, in_name, mtime in self.names.match(terms):
            full = in_name == len(terms)
            hits[fid] = ((10.0 if full else 1.0 + in_name) + mtime / 1e10, None, full)
        # Contents: the trigram index needs at least 3 characters
        long_terms = [t for t in terms if len(t) >= 3]
        if long_terms:
            match = " AND ".join('"' + t.replace('"', '""') + '"' for t in long_terms)
            try:
                rows = db.execute(
                    "SELECT c.file_id, c.id, bm25(chunks_fts) FROM chunks_fts "
                    "JOIN chunks c ON c.id = chunks_fts.rowid "
                    "WHERE chunks_fts MATCH ? AND c.kind = 1 ORDER BY bm25(chunks_fts) LIMIT ?",
                    (match, k)).fetchall()
            except sqlite3.Error:
                rows = []
            for r, (fid, cid, bm) in enumerate(rows):
                if fid not in hits:
                    hits[fid] = (0.5 - r / 1e4, cid, False)
                elif hits[fid][1] is None:
                    hits[fid] = (hits[fid][0], cid, hits[fid][2])
        return hits

    def _image_scores(self, q):
        """[(image file id, similarity)], best first."""
        with self.lock:
            ids, mat = getattr(self, "img_ids", None), getattr(self, "img_mat", None)
        if mat is None:
            return []
        from . import imagevec
        try:
            qv = imagevec.query_vector(q)
        except OSError:
            return []
        sc = mat @ qv
        if IMAGE_Z and len(sc) > 2 and (sc.max() - sc.mean()) / (sc.std() or 1) < IMAGE_Z:
            return []
        top = np.argsort(-sc)[:IMAGE_TOP * 5]
        return [(int(ids[i]), float(sc[i])) for i in top]

    def _gemma_list(self, q, images):
        """File ids by EmbeddingGemma similarity: each file's best chunk, and images (+IMAGE_OFFSET)."""
        with self.lock:
            fids, mat = getattr(self, "g_fids", None), getattr(self, "g_mat", None)
        if mat is None:
            return []
        from . import imagevec
        try:
            sc = _scores(mat, imagevec.query_vector(q))
        except OSError:
            return []
        k = min(500, len(sc))
        idx = np.argpartition(-sc, k - 1)[:k]
        best = {}
        for i in idx:
            f = int(fids[i])
            if sc[i] > best.get(f, -1.0):
                best[f] = float(sc[i])
        text_best = dict(best)
        for f, s in images[:IMAGE_TOP]:
            s += IMAGE_OFFSET
            if s > best.get(f, -1.0):
                best[f] = s
        top_text = max(text_best.values(), default=-1.0)
        self.gemma_photo_wins = {f for f, s in images[:IMAGE_TOP] if s + IMAGE_OFFSET >= top_text}
        return sorted(best, key=lambda f: -best[f])

    def _images(self, scores):
        """Separate image list: only photos close to the best match and above the floor."""
        if not scores:
            return []
        top = scores[0][1]
        keep = [f for f, s in scores if s >= max(top - IMAGE_GAP, IMAGE_FLOOR)]
        return keep[:IMAGE_TOP]

    def search(self, q, n=20, kind=None, rerank=True, group=True, cond=True):
        """group=True folds lower-ranked files from the same folder into the best one's
        "group" list (the app expands it with Tab). cond=False ignores time and source words."""
        t0 = time.time()
        q = q.strip()
        if not q:
            return {"results": [], "ms": 0, "reranked": False}
        db = self._db()
        # "上個月 LINE 傳來的報價單": search "報價單" among last month's files that came from LINE
        use_cond, cond, cond_info, allowed, sem_q = cond, None, None, None, q
        if use_cond and self.cfg.get("conditions"):
            rest, cond = conditions.parse(q)
            if cond:
                allowed = self.names.allowed(cond)
                src = cond.get("source")
                cond_info = {"time": cond.get("time"), "source": src[0] if src else None,
                             "matched": int(len(allowed))}
                if len(allowed):
                    sem_q = rest
                else:  # nothing meets them: say so, and search without them
                    cond, allowed = None, None
        kw_q, want_types = parse_types(sem_q) if sem_q else ("", None)
        if want_types and kw_q == sem_q.lower():
            sem_q = ""  # only type words were left ("上週的 PDF"): list the newest files of that type
        vec = self._vector(sem_q, allow=allowed) if sem_q else []
        kw = self._keyword(db, kw_q) if sem_q else {}

        # Rank name vectors and content vectors separately so long documents cannot flood results
        best_chunk, vec_score, name_score, content_score = {}, {}, {}, {}
        for cid, fid, ckind, sc in vec:
            bucket = name_score if ckind == 0 else content_score
            if fid not in bucket:
                bucket[fid] = sc
                if ckind == 1:
                    best_chunk[fid] = cid
            vec_score[fid] = max(vec_score.get(fid, sc), sc)
        lookup = is_lookup(kw_q)
        images = []
        if self.cfg.get("image_search") and sem_q and not lookup and (not want_types or want_types & config.IMAGE_EXT):
            images = self._image_scores(sem_q)
        shared = embed._name and "embeddinggemma" in embed._name.lower()
        gemma_list = self._gemma_list(sem_q, images) if self.cfg.get("gemma_channel") and sem_q and not shared else []
        if images and shared:
            for fid, sc in images[:IMAGE_TOP]:
                sc += IMAGE_OFFSET
                if sc > content_score.get(fid, -1.0):
                    content_score[fid] = sc
                    vec_score[fid] = max(vec_score.get(fid, sc), sc)
            content_score = dict(sorted(content_score.items(), key=lambda x: -x[1]))
        kw_sorted = sorted(kw.items(), key=lambda x: -x[1][0])
        kw_rank = {fid: r for r, (fid, _) in enumerate(kw_sorted)}

        vec_w, kw_w = (LOOKUP_VEC, LOOKUP_KW) if lookup else (1.0, 1.0)
        fused = {}
        for bucket, w in ((name_score, W_NAME), (content_score, W_CONTENT)):
            for r, fid in enumerate(bucket):
                fused[fid] = fused.get(fid, 0) + vec_w * w / (RRF_K + r)
        if W_SIM and content_score:
            top = max(content_score.values())
            for fid, sc in content_score.items():
                fused[fid] = fused.get(fid, 0) + vec_w * W_SIM * max(0.0, sc - top + 0.15)
        for fid, r in kw_rank.items():
            score, cid, full_name = kw[fid]
            w = kw_w * (1.6 if full_name else 1.0)
            fused[fid] = fused.get(fid, 0) + w / (RRF_K + r)
            if fid not in best_chunk and cid:
                best_chunk[fid] = cid
        wins = getattr(self, "gemma_photo_wins", set()) if gemma_list else set()
        for r, fid in enumerate(gemma_list):
            m = IMAGE_MULT if fid in wins else 1.0
            fused[fid] = fused.get(fid, 0) + m * vec_w * W_GEMMA / (RRF_K + r)
        if images and not shared and not gemma_list:
            for r, fid in enumerate(self._images(images)):
                fused[fid] = fused.get(fid, 0) + W_IMAGE / (RRF_K + r)
        if cond:
            allowed_set = set(allowed.tolist())
            fused = {f: v for f, v in fused.items() if f in allowed_set}
            if not fused:  # no words to search for: newest first
                newest = sorted(allowed_set, key=lambda f: -self.names.mtime_of(f))
                fused = {f: 1.0 / (RRF_K + r) for r, f in enumerate(newest[:500])}
        if want_types and ".app" in want_types:
            # Explicitly asked for an app: list apps only, re-ranking all of them by name
            app_scores = self._app_vector(q)
            fused = {f: fused.get(f, 0) + 1.0 / (RRF_K + r) for r, f in enumerate(app_scores)}
        elif want_types:
            for fid, ext, is_dir in self.names.types(list(fused)):
                key = "<dir>" if is_dir else ext
                fused[fid] *= 1.6 if key in want_types else 0.6
        # The query is exactly an app name (e.g. "Photos" / "照片"): that app goes first
        for fid in self.names.exact_apps(q):
            fused[fid] = max(fused.values(), default=0) + 1
        self._usage_boost(fused, q)
        order = sorted(fused, key=lambda f: -fused[f])
        reranked, rel = False, {}
        if rerank and (self.reranker or self.remote) and order:
            order, reranked, rel = self._rerank(db, sem_q or q, order, best_chunk, kw)

        results, seen = match_places(q), {}
        limit = n * 4 if group else n  # more candidates before folding folders together
        for fid in order:
            if len(results) >= limit:
                break
            row = db.execute("SELECT path, name, ext, size, mtime, is_dir, dataless, note "
                             "FROM files WHERE id=?", (fid,)).fetchone()
            if not row:
                continue
            path, name, ext, size, mtime, is_dir, dataless, note = row
            if kind == "folder" and not is_dir:
                continue
            if not _exists(path):
                continue
            key = (name, size) if not is_dir else None
            if key and key in seen:  # list copies of the same file once
                seen[key]["copies"] += 1
                continue
            snippet, where, chunk = "", "name", ""
            cid = best_chunk.get(fid)
            if cid:
                c = db.execute("SELECT kind, text, file_id FROM chunks WHERE id=?", (cid,)).fetchone()
                if c and c[0] == 1 and c[2] == fid and not extract.garbled(c[1]):
                    # chunk ids can be reused: check ownership; hide garbled text
                    snippet, where, chunk = _snippet(c[1], sem_q or q), "content", c[1]
            if fid in kw and kw[fid][2]:
                where = "name"
            results.append({
                "path": path, "name": name, "ext": ext, "size": size,
                "mtime": mtime, "is_dir": bool(is_dir), "cloud": bool(dataless),
                "note": note or "", "snippet": snippet, "match": where,
                "hits": [], "best": "", "page": None, "_chunk": chunk,
                "score": round(fused[fid] * 1000, 2),
                "semantic": round(vec_score.get(fid, 0.0), 3),
                "rel": round(rel[fid], 3) if fid in rel else None,  # reranker logit
                "exact": bool(fid in kw and kw[fid][2]),  # the query is the file name
                "copies": 0,
            })
            if key:
                seen[key] = results[-1]
        db.close()
        if reranked:
            results = _tiers(results, len(rel))
        places = {r["path"] for r in results if r["match"] == "place"}
        results = [r for r in results if r["match"] == "place" or r["path"] not in places]
        if group:
            results = _group_by_folder(results)
        results = results[:n]
        # the closest sentence takes about 0.3 s: only for the request after typing pauses
        self._explain(results, sem_q or q, [g for r in results for g in r.get("group", [])], deep=rerank)
        out = {"results": results, "ms": int((time.time() - t0) * 1000), "reranked": reranked}
        if cond_info:
            out["conditions"] = cond_info
        return out

    def _qvec(self, q):
        """The query's vector, computed once per query: the file, app and sentence steps all use it."""
        key = (embed._name, q)
        v = self._qcache.get(key)
        if v is None:
            v = embed.encode([q], kind="query")
            if len(self._qcache) > 64:
                self._qcache.clear()
            self._qcache[key] = v
        return v

    def _explain(self, results, q, others=(), deep=True, top=3):
        """Why each result matched, for the panel: the sentence of its best passage that is
        closest in meaning to the query ("best", any language) and the query words it contains
        ("hits"), with the snippet centred on that sentence, and a PDF's page number. others
        (folded same-folder files) and results below the first `top` only get the words."""
        todo = [r for r in results if r.get("_chunk")][:top] if deep else []
        sents = [_sentences(r["_chunk"], most=8) for r in todo]
        flat = [x for ss in sents for x in ss]
        if flat and q:
            try:
                # long sentences are cut for the model: their start is enough to tell what they say
                short = [x[:SENT_CHARS] for x in flat]
                qv = self._qvec(q)[0]
                if self.torch:
                    with self.gpu:
                        sv = embed.encode(short, kind="query")
                else:
                    sv = embed.encode(short, kind="query")
                sc, i, first = sv @ qv, 0, None
                for r, ss in zip(todo, sents):
                    if ss:
                        j = int(np.argmax(sc[i:i + len(ss)]))
                        r["_around"] = ss[j]
                        # Highlight only a clear answer: the first result's sentence, and another's
                        # when it is about as close; elsewhere the snippet just starts there
                        first = sc[i + j] if first is None else first
                        if sc[i + j] >= (0.4 if r is todo[0] else max(0.55, first - 0.05)):
                            r["best"] = ss[j]
                    i += len(ss)
            except Exception:
                pass
        for r in [*results, *others]:
            chunk = r.pop("_chunk", "")
            if not chunk:
                continue
            around = r.pop("_around", "")
            if around:
                r["snippet"] = _snippet(chunk, q, around=around)
            r["hits"] = _hit_words(r["snippet"], q)
            if r["ext"] == ".pdf" and not r["cloud"]:
                r["page"] = _pdf_page(r["path"], r["mtime"], [around or r["snippet"], chunk])

    def status(self):
        db = self._db()
        out = {k: v for k, v in db.execute("SELECT k, v FROM meta")}
        out["files"] = int(len(self.names.ids))  # already in memory; counting the DB is slow
        out["chunks"] = int(len(self.chunk_ids)) if self.chunk_ids is not None else 0
        db.close()
        return out


class _NameIndex:
    """All names and folder paths in one in-memory string; str.find is much faster than SQL LIKE."""

    def __init__(self, db):
        rows = db.execute("SELECT id, name, parent, mtime, ext, is_dir FROM files").fetchall()
        try:
            self.src = dict(db.execute("SELECT id, src FROM files WHERE src != ''"))
        except sqlite3.Error:  # index from before sources were recorded
            self.src = {}
        db.close()
        self.ids = np.array([r[0] for r in rows], dtype=np.int64)
        self.kind = {r[0]: (r[4], r[5]) for r in rows}
        # Localized app names ("照片（Photos.app）" → "照片") and plain ones
        self.app_names = {}
        for r in rows:
            if r[4] == ".app":
                self.app_names[r[0]] = r[1].split("（")[0].removesuffix(".app").lower()
        self.mtime = np.array([r[3] or 0 for r in rows], dtype=np.float64)
        names = [r[1].lower().replace("\n", " ") for r in rows]
        self.blob = "\n".join(names)
        self.starts = np.cumsum([0] + [len(n) + 1 for n in names[:-1]]) if names else np.zeros(0)
        parents = {}
        for i, r in enumerate(rows):
            parents.setdefault(r[2].lower(), []).append(i)
        self.parent_keys = list(parents)
        self.parent_rows = [np.array(v) for v in parents.values()]
        self.parent_blob = "\n".join(k.replace("\n", " ") for k in self.parent_keys)
        self.parent_starts = np.cumsum([0] + [len(k) + 1 for k in self.parent_keys[:-1]]) \
            if self.parent_keys else np.zeros(0)

    def allowed(self, cond):
        """File ids that meet the conditions (conditions.parse)."""
        ok = np.ones(len(self.ids), dtype=bool)
        if "after" in cond:
            ok &= (self.mtime >= cond["after"]) & (self.mtime < cond["before"])
        if cond.get("source"):
            fit = {f for f, s in self.src.items() if conditions.source_matches(s, cond["source"])}
            ok &= np.isin(self.ids, np.fromiter(fit, dtype=np.int64, count=len(fit)))
        return self.ids[ok]

    def mtime_of(self, fid):
        if not hasattr(self, "_row"):
            self._row = {int(f): i for i, f in enumerate(self.ids)}
        i = self._row.get(fid)
        return float(self.mtime[i]) if i is not None else 0.0

    def exact_apps(self, q):
        q = q.strip().lower()
        return [f for f, (ext, _) in self.kind.items()
                if ext == ".app" and q and self.app_names.get(f) == q]

    def types(self, fids):
        return [(f, *self.kind.get(f, ("", 0))) for f in fids]

    @staticmethod
    def _find(blob, starts, term):
        pos, out = 0, []
        while True:
            pos = blob.find(term, pos)
            if pos < 0:
                return np.unique(np.searchsorted(starts, np.array(out), side="right") - 1) if out else []
            out.append(pos)
            pos += 1

    def match(self, terms, parent_limit=3000):
        """Return [(file id, number of terms in the name, mtime)]."""
        count = {}
        for t in terms:
            for i in self._find(self.blob, self.starts, t.lower()):
                count[i] = count.get(i, 0) + 1
        out = [(int(self.ids[i]), c, float(self.mtime[i])) for i, c in count.items()]
        if len(terms) == 1:
            rows = [self.parent_rows[k] for k in self._find(self.parent_blob, self.parent_starts, terms[0].lower())]
            if rows:
                idx = np.concatenate(rows)
                idx = idx[np.argsort(-self.mtime[idx])][:parent_limit]
                out += [(int(self.ids[i]), 0, float(self.mtime[i])) for i in idx if i not in count]
        return out


def _tiers(results, judged=TIER_SPAN):
    """Tier by reranker score: 1 = best matches, 2 = less related; drop the weak rest.
    Places and exact file-name matches are always in the first tier. `judged` is how many
    files the reranker scored; unscored files come after them in fast-search order."""
    scores = [r["rel"] for r in results if r.get("rel") is not None]
    if not scores:
        return results
    # a place or an exact file name is a sure answer (logit 0): other files are measured against it
    sure = any(r["match"] == "place" or r.get("exact") for r in results)
    top = max(scores + ([0.0] if sure else []))
    tier1 = top - TIER1_GAP
    shown = max(top - SHOW_GAP, SHOW_FLOOR)
    unjudged = TIER_SPAN - judged  # unscored files still kept, to rank TIER_SPAN
    out = []
    for r in results:
        if r["match"] == "place" or r.get("exact"):
            r["tier"] = 1
        elif r.get("rel") is None:
            if unjudged <= 0:
                continue  # beyond the candidates a full reranker window would have judged
            unjudged -= 1
            r["tier"] = 2
        elif r["rel"] < shown:
            continue  # too weak
        else:
            r["tier"] = 1 if r["rel"] >= tier1 else 2
        out.append(r)
    if not out and results:  # never an empty list: conditions can leave only weak matches
        out = [dict(results[0], tier=2)]
    return sorted(out, key=lambda r: r["tier"])  # stable: keeps the order within each tier


def _group_by_folder(results, max_group=30):
    """Keep only the best-ranked file of each folder; later files from the same folder go
    into its "group" list. Folders, apps and places are never folded."""
    heads, by_parent = [], {}
    for r in results:
        r["group"] = []
        if r["is_dir"] or r["match"] == "place" or r["ext"] == ".app":
            heads.append(r)
            continue
        parent = os.path.dirname(r["path"])
        head = by_parent.get(parent)
        if head is None:
            by_parent[parent] = r
            heads.append(r)
        elif len(head["group"]) < max_group:
            head["group"].append({k: v for k, v in r.items() if k != "group"})
    return heads


def _exists(path):
    """Missing only if deleted; a permission error (macOS access not granted yet) counts as present."""
    try:
        os.stat(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _snippet(text, q, width=140, around=""):
    text = text.replace("\n", " ")
    low = text.lower()
    # start at the given sentence, else a little before the first query word the text contains
    pos = text.find(around.replace("\n", " ")) if around else -1
    start = pos
    if pos < 0:
        pos = min((p for w in _hit_words(text, q) for p in [low.find(w.lower())] if p >= 0), default=-1)
        start = max(0, pos - width // 3)
    if pos < 0:
        return text[:width] + ("…" if len(text) > width else "")
    s = text[start:start + width]
    return ("…" if start else "") + s + ("…" if start + width < len(text) else "")


def _sentences(text, most=12):
    """A passage cut at sentence ends and line breaks into pieces of 8 to 200 characters, each
    an exact slice of the text (so the snippet can be found and highlighted)."""
    spans, start = [], 0
    for m in re.finditer(r"[。！？；!?;]|\.(?=\s)|\n+", text):
        if m.group().startswith("\n") and re.match(r"[a-z]", text[m.end():m.end() + 1]) \
                and re.search(r"[a-z,-][ \t]*$", text[max(0, m.start() - 3):m.start()]):
            continue  # a PDF line break inside a sentence
        spans.append((start, m.end()))
        start = m.end()
    spans.append((start, len(text)))
    out = []
    for a, b in spans:
        piece = text[a:b].strip()
        if not piece:
            continue
        prev = text[out[-1][0]:out[-1][1]].strip() if out else ""
        if prev and len(prev) < 25 and not re.search(r"[。！？!?.]$", prev):  # a heading or label goes with what follows
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    pieces = [text[a:b].strip().lstrip("#*-> ").strip() for a, b in out]
    return [p for p in pieces if 8 <= len(p) <= 200][:most]


_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
_FILLER = set("的了是在我你他她它們们和與与及有這这那個个一之要找")


def _hit_words(text, q, most=6):
    """The query's words as they appear in the text, for the app to draw in bold. A Chinese,
    Japanese or Korean query has no spaces, so its longest pieces (2+ characters) found in
    the text count; English words also match without a plural or -ed/-ing ending."""
    low, out = text.lower(), []
    for t in _terms(q):
        t = t.lower()
        if not _CJK.search(t):
            for w in (t, re.sub(r"(es|s|ed|ing)$", "", t)):
                if len(w) >= 2 and w not in STOPWORDS and re.search(rf"(?<![a-z0-9]){re.escape(w)}", low):
                    out.append(w)
                    break
            continue
        i = 0
        while i < len(t) - 1:
            j = next((j for j in range(len(t), i + 1, -1) if t[i:j] in low), None)
            if j and not set(t[i:j]) <= _FILLER:
                out.append(t[i:j])
                i = j
            else:
                i += 1
    out = sorted(set(out), key=len, reverse=True)
    return out[:most]


_pages = {}


def _pdf_page(path, mtime, probes):
    """1-based page of a PDF that holds the given text (the snippet, else the chunk), or None."""
    key = (path, mtime, probes[0][:80])
    if key in _pages:
        return _pages[key]
    squash = lambda s: re.sub(r"[\s…]+", "", s)
    keys = []
    for p in probes:
        p = squash(p)
        if len(p) >= 12:
            mid = len(p) // 2
            keys.append(p[max(0, mid - 12):mid + 12])
    page = None
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(path)
        try:
            texts = [squash(doc[i].get_textpage().get_text_range()) for i in range(min(len(doc), 300))]
        finally:
            doc.close()
        page = next((i + 1 for k in keys for i, t in enumerate(texts) if k in t), None)
    except Exception:
        pass
    if len(_pages) > 500:
        _pages.clear()
    _pages[key] = page
    return page
