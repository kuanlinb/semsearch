"""Measure retrieval quality on your own files, and compare embedding models.

    python eval/run_eval.py --queries my_queries.json --roots ~/Documents ~/Downloads \
        --model BAAI/bge-m3 --tag bgem3

queries file: a JSON list of [query, expected] pairs. `expected` is a substring of the
right file's name; use "a|b" when several files are acceptable. See queries.example.json.
Each (model, tag) gets its own throwaway index under ~/.semsearch_eval/<tag>.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", required=True)
    ap.add_argument("--roots", nargs="+", required=True)
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--reranker", default="")
    ap.add_argument("--reindex", action="store_true")
    a = ap.parse_args()

    data = os.path.expanduser(f"~/.semsearch_eval/{a.tag}")
    os.makedirs(data, exist_ok=True)
    json.dump({"roots": [os.path.expanduser(r) for r in a.roots], "hot_roots": [],
               "model": a.model, "reranker": a.reranker}, open(f"{data}/config.json", "w"))
    os.environ["SEMSEARCH_DATA"] = data
    t = time.time()
    # An existing index for this --tag is reused; pass --reindex after changing --roots
    if a.reindex or not os.path.exists(f"{data}/index.db"):
        subprocess.run([sys.executable, "-m", "semsearch.indexer"], cwd=HERE, check=True)
    index_s = time.time() - t

    sys.path.insert(0, HERE)
    from semsearch.search import Searcher
    s = Searcher()
    qs = json.load(open(a.queries))
    mrr = h1 = h5 = h10 = 0
    ms = []
    for q, want in qs:
        res = s.search(q, n=10)
        ms.append(res["ms"])
        # A row also counts when the file is folded into it (same folder, shown with Tab)
        rows = [[os.path.basename(x["path"]).lower() for x in [r] + r.get("group", [])]
                for r in res["results"]]
        names = [r[0] for r in rows]
        rank = next((i + 1 for i, ns in enumerate(rows)
                     if any(w.lower() in n for n in ns for w in want.split("|"))), None)
        mrr += 1 / rank if rank else 0
        h1 += rank == 1
        h5 += bool(rank and rank <= 5)
        h10 += bool(rank)
        print(f"{rank or '-':>2}  {q}  →  {names[0] if names else ''}")
    n = len(qs)
    print(f"[{a.tag}] hit@1={h1}/{n} hit@5={h5}/{n} hit@10={h10}/{n} MRR={mrr / n:.3f} "
          f"index={index_s:.0f}s median_search={sorted(ms)[n // 2]}ms")


if __name__ == "__main__":
    main()
