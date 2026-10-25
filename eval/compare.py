"""Compare ranking features on an index built by run_eval.py (no re-indexing):
the plain hybrid ranking vs. usage boost (recently opened files) and same-folder grouping.

    python eval/compare.py --queries my_queries.json --tag bgem3 [--exact]

With --exact, `expected` must equal the file name instead of being a substring.
With grouping on, a file folded into a row (same folder, Tab in the app) counts for that row.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("--queries", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("--exact", action="store_true")
a = ap.parse_args()
os.environ["SEMSEARCH_DATA"] = os.path.expanduser(f"~/.semsearch_eval/{a.tag}")
sys.path.insert(0, HERE)
from semsearch import search  # noqa: E402

s = search.Searcher()
qs = json.load(open(a.queries))


def ok(name, want):
    if a.exact:
        return name == want
    return any(w.lower() in name.lower() for w in want.split("|"))


def score(group):
    h1 = h5 = h10 = 0
    for q, want in qs:
        res = s.search(q, n=10, rerank=False, group=group)["results"]
        rows = [[os.path.basename(x["path"]) for x in [r] + r.get("group", [])] for r in res]
        rank = next((i + 1 for i, ns in enumerate(rows) if any(ok(n, want) for n in ns)), None)
        h1 += rank == 1
        h5 += bool(rank and rank <= 5)
        h10 += bool(rank)
    return f"{h1:>3} / {h5:>3} / {h10:>3}"


defaults = dict(W_RECENT=search.W_RECENT, W_OPENS=search.W_OPENS, W_SAME_QUERY=search.W_SAME_QUERY)
configs = [
    ("plain", dict(W_RECENT=0, W_OPENS=0, W_SAME_QUERY=0), False),
    ("+ usage boost", defaults, False),
    ("+ usage + grouping", defaults, True),
]
print(f"{len(qs)} queries; hits at #1 / top 5 / top 10")
for name, weights, group in configs:
    for k, v in weights.items():
        setattr(search, k, v)
    print(f"{name:<22} {score(group)}", flush=True)
