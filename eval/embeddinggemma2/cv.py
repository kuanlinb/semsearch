"""Score tune.py grids fairly: pick the weights on a random half of the questions, count Hit@1 on
the other half, 500 times; also the default weights and the best weights on all questions
(optimistic: chosen on the same questions they are scored on).

    python eval/embeddinggemma2/cv.py results/eg2_tune_bgem3.json results/eg2_tune_B.json
"""
import json
import random
import sys

DEFAULT = {"W_NAME": 1.0, "W_CONTENT": 1.0, "RRF_K": 20, "W_SIM": 0.4, "W_GEMMA": 1.0}


def stats(ranks, idx):
    return (sum(ranks[i] == 1 for i in idx), sum(1 / ranks[i] for i in idx if ranks[i]))


def main():
    for path in sys.argv[1:]:
        d = json.load(open(path))
        rows, n = d["rows"], len(d["questions"])
        every = range(n)
        default = next(r for r in rows if all(r["w"].get(k, v) == v for k, v in DEFAULT.items()))
        best = max(rows, key=lambda r: stats(r["ranks"], every))
        rng = random.Random(0)
        held = []
        for _ in range(500):
            train = set(rng.sample(range(n), n // 2))
            test = [i for i in every if i not in train]
            pick = max(rows, key=lambda r: stats(r["ranks"], train))
            held.append(2 * stats(pick["ranks"], test)[0])  # scaled to all n questions
        print(f"{d['tag']:<22} default {stats(default['ranks'], every)[0]}/{n}"
              f"  best on all {stats(best['ranks'], every)[0]} {best['w']}"
              f"  held-out mean {sum(held) / len(held):.1f}")


if __name__ == "__main__":
    main()
