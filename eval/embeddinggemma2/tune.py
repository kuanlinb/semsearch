"""Grid-search the fusion weights on an eval index, keeping every question's rank, so a fair
comparison can pick weights on one half of the questions and score them on the other.

    python eval/embeddinggemma2/tune.py <tag> <corpus> <queries.json> <out.json> [tags to use, e.g. photo-zh]

Only the text questions (no "photo" tag) are searched unless tags are given. TUNE_GRID (JSON, same
shape as GRID) replaces the grid, e.g. to add W_GEMMA for the two-model setup.
"""
import itertools
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GRID = {"W_NAME": [0.5, 1.0, 1.5], "W_CONTENT": [0.5, 1.0, 1.5, 2.0], "RRF_K": [10, 20, 40, 60],
        "W_SIM": [0.0, 0.4, 0.8, 1.2]}
GRID = json.loads(os.environ.get("TUNE_GRID", "null")) or GRID


def main():
    tag, corpus, queries, out = sys.argv[1:5]
    tags = set(sys.argv[5:])
    os.environ["SEMSEARCH_DATA"] = os.path.expanduser(f"~/.semsearch_eval/{tag}")
    sys.path.insert(0, REPO)
    from semsearch import search
    s = search.Searcher()
    corpus = os.path.abspath(os.path.expanduser(corpus))
    qs = [q for q in json.load(open(queries))["queries"]
          if (q.get("tag", "") in tags if tags else "photo" not in q.get("tag", ""))]
    rows = []
    for combo in itertools.product(*GRID.values()):
        for k, v in zip(GRID, combo):
            setattr(search, k, v)
        ranks = []
        for q in qs:
            want = {os.path.join(corpus, p) for p in q["expect"]}
            files = [r["path"] for r in s.search(q["q"], n=50, group=False, rerank=False)["results"]
                     if not r["is_dir"] and not r["path"].endswith(".app")]
            ranks.append(next((i + 1 for i, p in enumerate(files) if p in want), None))
        rows.append({"w": dict(zip(GRID, combo)), "ranks": ranks})
        print(dict(zip(GRID, combo)), sum(r == 1 for r in ranks), flush=True)
    json.dump({"tag": tag, "questions": [q["q"] for q in qs], "rows": rows}, open(out, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
