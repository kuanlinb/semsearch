"""Save what the reranker would read for every query: the fast-search order (top 40 files) and the
text built for each, so rerankers can be compared offline on exactly the same candidates.

    SEMSEARCH_DATA=~/.semsearch_eval/<tag> python eval/local_rerank/collect.py <queries.json> <corpus> <out.json>

queries.json: {"queries": [{"q": ..., "expect": [paths relative to corpus]}]} (eval/lookalike format).
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from semsearch.search import Searcher  # noqa: E402

qfile, corpus, out = sys.argv[1], os.path.abspath(os.path.expanduser(sys.argv[2])), sys.argv[3]
s = Searcher()
seen = {}
# Pretend a remote reranker is up: _rerank builds the texts, the capture returns None, so the
# fast order is kept unchanged
s.remote, s.remote_ok = "capture", True
s._remote_scores = lambda q, texts: seen.setdefault("texts", texts) and None
rows = []
for item in json.load(open(qfile))["queries"]:
    seen.clear()
    orig = s._rerank

    def grab(db, q, order, best_chunk, kw):
        seen["order"] = order[:40]
        seen["bonus"] = [bool(f in kw and kw[f][2]) for f in order[:40]]
        seen["paths"] = [db.execute("SELECT path, is_dir FROM files WHERE id=?", (f,)).fetchone() for f in order[:40]]
        return orig(db, q, order, best_chunk, kw)
    s._rerank = grab
    res = s.search(item["q"], n=50, group=False)
    s._rerank = orig
    paths = [p for p, _ in seen["paths"]]
    rows.append({**item, "cands": [os.path.relpath(p, corpus) if p.startswith(corpus) else p for p in paths],
                 "is_file": [not d and not p.endswith(".app") for p, d in seen["paths"]],
                 "name_bonus": seen["bonus"], "texts": seen["texts"], "ms": res["ms"]})
json.dump({"corpus": corpus, "queries": rows}, open(out, "w"), ensure_ascii=False, indent=1)
print("wrote", out, len(rows))
