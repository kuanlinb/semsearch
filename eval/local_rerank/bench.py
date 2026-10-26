"""Time and memory of the local int8 reranker next to the int8 bge-m3 encoder, as the search
service would hold them.

    python eval/local_rerank/bench.py <cands.json> <reranker dir> [threads ...]

Rounds alternate between settings so a busy machine slows all of them alike. Prints the median
time to score the top 5 and top 10 candidates at 256 and 128 tokens, and resident memory after
loading the encoder, after loading the reranker, and at the peak.
"""
import json
import os
import resource
import statistics
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from semsearch import embed  # noqa: E402


def rss_mb():
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout
    return round(int(out) / 1024)


cands, folder = sys.argv[1], sys.argv[2]
threads = [int(t) for t in sys.argv[3:]] or [4]
rows = json.load(open(cands))["queries"][:30]
base = rss_mb()
embed.get_model("BAAI/bge-m3")
embed.encode(["warm up"], kind="query")
enc = rss_mb()
out = {"rss_start_mb": base, "rss_with_encoder_mb": enc}
for th in threads:
    os.environ["SEMSEARCH_THREADS"] = str(th)
    rr = {256: embed.OnnxReranker(folder, max_tokens=256)}
    rr[256].scores(rows[0]["q"], rows[0]["texts"][:5])
    out.setdefault("rss_with_reranker_mb", rss_mb())  # one reranker loaded and used once
    rr[128] = embed.OnnxReranker(folder, max_tokens=128)
    times = {(n, k): [] for n in rr for k in (5, 10)}
    for _ in range(2):
        for r in rows:
            for (n, k), ts in times.items():
                t = time.perf_counter()
                rr[n].scores(r["q"], r["texts"][:k])
                ts.append(time.perf_counter() - t)
    for (n, k), ts in times.items():
        out[f"threads{th}_top{k}_{n}tok_ms"] = round(statistics.median(ts) * 1000)
out["rss_peak_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20)
out["load"] = os.getloadavg()[0]
print(json.dumps(out))
