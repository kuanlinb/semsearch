"""Grid-search the fusion weights on an index built by run_eval.py (no re-indexing).

    python eval/tune.py --queries my_queries.json --tag bgem3
"""
import argparse
import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("--queries", required=True)
ap.add_argument("--tag", required=True)
a = ap.parse_args()
os.environ["SEMSEARCH_DATA"] = os.path.expanduser(f"~/.semsearch_eval/{a.tag}")
sys.path.insert(0, HERE)
from semsearch import search  # noqa: E402

s = search.Searcher()
qs = json.load(open(a.queries))


def score():
    mrr = h1 = 0
    for q, want in qs:
        names = [os.path.basename(x["path"]).lower() for x in s.search(q, n=10, group=False)["results"]]
        rank = next((i + 1 for i, n in enumerate(names)
                     if any(w.lower() in n for w in want.split("|"))), None)
        mrr += 1 / rank if rank else 0
        h1 += rank == 1
    return h1, round(mrr / len(qs), 3)


print("W_NAME W_CONTENT RRF_K hit@1 MRR")
for wn, wc, k in itertools.product([0.7, 1.0, 1.5], [0.7, 1.0, 1.5], [20, 60]):
    search.W_NAME, search.W_CONTENT, search.RRF_K = wn, wc, k
    print(wn, wc, k, *score(), flush=True)
