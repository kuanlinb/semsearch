"""Search quality on the look-alike test set (see README.md here).

    .venv/bin/python eval/lookalike/make_corpus.py ~/semsearch-lookalike
    nice -n 15 .venv/bin/python eval/lookalike/run.py --corpus ~/semsearch-lookalike --tag bge-m3
    nice -n 15 .venv/bin/python eval/lookalike/run.py --corpus ~/semsearch-lookalike --tag bge-m3_reranker \
        --reranker BAAI/bge-reranker-v2-m3

Indexes the corpus into a throwaway index under ~/.semsearch_eval/<tag> (like eval/run_eval.py) and
writes results/<tag>.json: for every query the ranked list, the rank of the expected file among
files (folders and apps skipped), the rank as the panel shows it (same-folder grouping on, a file
folded into a row counts at that row) and the search time.
"""
import argparse
import json
import os
import resource
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, help="folder made by make_corpus.py")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--reranker", default="")
    ap.add_argument("--reindex", action="store_true")
    ap.add_argument("--queries", default=os.path.join(HERE, "queries.json"))
    ap.add_argument("--config", default="{}", help='extra config keys as JSON, e.g. \'{"image_search": true}\'')
    a = ap.parse_args()
    corpus = os.path.abspath(os.path.expanduser(a.corpus))

    data = os.path.expanduser(f"~/.semsearch_eval/{a.tag}")
    if a.reindex:  # start empty: an index of another --corpus would keep its files
        shutil.rmtree(data, ignore_errors=True)
    os.makedirs(data, exist_ok=True)
    json.dump({"roots": [corpus], "hot_roots": [], "model": a.model, "reranker": a.reranker,
               **json.loads(a.config)}, open(f"{data}/config.json", "w"))
    os.environ["SEMSEARCH_DATA"] = data
    index_s = None
    if a.reindex or not os.path.exists(f"{data}/index.db"):
        t = time.time()
        subprocess.run([sys.executable, "-m", "semsearch.indexer"], cwd=REPO, check=True)
        index_s = round(time.time() - t, 1)
    index_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss  # bytes on macOS

    sys.path.insert(0, REPO)
    from semsearch.search import Searcher
    t = time.time()
    s = Searcher()
    load_s = round(time.time() - t, 1)
    s.search("warm up", n=10)

    qs = json.load(open(a.queries))["queries"]
    rows = []
    for item in qs:
        want = {os.path.join(corpus, p) for p in item["expect"]}
        t = time.time()
        flat = s.search(item["q"], n=50, group=False)
        wall_ms = (time.time() - t) * 1000
        grouped = s.search(item["q"], n=10)
        files = [r["path"] for r in flat["results"] if not r["is_dir"] and not r["path"].endswith(".app")]
        rank = next((i + 1 for i, p in enumerate(files) if p in want), None)
        panel = next((i + 1 for i, r in enumerate(grouped["results"])
                      if any(x["path"] in want for x in [r] + r.get("group", []))), None)
        rows.append({**item, "rank": rank, "panel_rank": panel, "ms": flat["ms"], "wall_ms": round(wall_ms, 1),
                     "reranked": flat["reranked"],
                     "top": [os.path.relpath(r["path"], corpus) if r["path"].startswith(corpus) else r["path"]
                             for r in flat["results"][:5]]})
        print(f"{rank or '-':>2} {panel or '-':>2}  {flat['ms']:>5}ms  {item['q']}  →  {rows[-1]['top'][:1]}")

    n = len(rows)
    summary = {
        "tag": a.tag, "model": a.model, "reranker": a.reranker or None, "n": n,
        "hit1": sum(r["rank"] == 1 for r in rows), "hit3": sum(bool(r["rank"] and r["rank"] <= 3) for r in rows),
        "panel_hit1": sum(r["panel_rank"] == 1 for r in rows),
        "panel_hit3": sum(bool(r["panel_rank"] and r["panel_rank"] <= 3) for r in rows),
        "mrr": round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3),
        "mean_ms": round(sum(r["ms"] for r in rows) / n, 1),
        "median_ms": sorted(r["ms"] for r in rows)[n // 2],
        "index_s": index_s, "searcher_load_s": load_s,
        "index_peak_rss_mb": round(index_rss / 2**20), "search_peak_rss_mb":
            round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20),
        "index_db_mb": round(os.path.getsize(f"{data}/index.db") / 2**20, 2),
    }
    print(json.dumps(summary, ensure_ascii=False))
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    json.dump({"summary": summary, "queries": rows}, open(os.path.join(HERE, "results", f"{a.tag}.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
