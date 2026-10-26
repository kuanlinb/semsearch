"""Hit@1 / Hit@3 for text and photo questions under given fusion weights, on an eval index.

    python eval/embeddinggemma2/check.py <tag> <corpus> <queries.json> '[{"W_SIM": 1.2, ...}, ...]'

Weights left out keep the defaults in semsearch/search.py.
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    tag, corpus, queries, sets = sys.argv[1:5]
    os.environ["SEMSEARCH_DATA"] = os.path.expanduser(f"~/.semsearch_eval/{tag}")
    sys.path.insert(0, REPO)
    from semsearch import search
    s = search.Searcher()
    corpus = os.path.abspath(os.path.expanduser(corpus))
    qs = json.load(open(queries))["queries"]
    base = {k: getattr(search, k) for w in json.loads(sets) for k in w}
    for w in json.loads(sets):
        for k, v in {**base, **w}.items():
            setattr(search, k, v)
        got = {}
        for q in qs:
            want = {os.path.join(corpus, p) for p in q["expect"]}
            files = [r["path"] for r in s.search(q["q"], n=50, group=False, rerank=False)["results"]
                     if not r["is_dir"] and not r["path"].endswith(".app")]
            rank = next((i + 1 for i, p in enumerate(files) if p in want), None)
            group = q.get("tag", "") if "photo" in q.get("tag", "") else "text"
            h = got.setdefault(group, [0, 0, 0])
            h[0] += rank == 1
            h[1] += bool(rank and rank <= 3)
            h[2] += 1
        print(tag, w, "  ".join(f"{g} {a}/{b} of {n}" for g, (a, b, n) in got.items()), flush=True)


if __name__ == "__main__":
    main()
