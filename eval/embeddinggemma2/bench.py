"""python bench.py <tag> <corpus>: model-only speed/memory + vector-only accuracy on an eval index."""
import json, os, sys, time, resource, sqlite3, statistics
tag, corpus = sys.argv[1], sys.argv[2]
data = os.path.expanduser(f"~/.semsearch_eval/{tag}")
os.environ["SEMSEARCH_DATA"] = data
sys.path.insert(0, os.getcwd())
import psutil
proc = psutil.Process()
rss0 = proc.memory_info().rss
from semsearch import embed, config
model = json.load(open(f"{data}/config.json"))["model"]
t = time.time(); embed.get_model(model); load_s = time.time() - t
rss_model = proc.memory_info().rss
db = sqlite3.connect(f"{data}/index.db")
chunks = [r[0] for r in db.execute("SELECT text FROM chunks WHERE kind=1 ORDER BY length(text) DESC LIMIT 256")]
avg_chars = sum(map(len, chunks)) / len(chunks)
embed.encode(chunks[:16])
t = time.time(); embed.encode(chunks); thr = len(chunks) / (time.time() - t)
qs = json.load(open("eval/lookalike/queries.json"))["queries"]
embed.encode(["warm"], kind="query")
lat = []
for q in qs:
    t = time.time(); embed.encode([q["q"]], kind="query"); lat.append((time.time() - t) * 1000)
from semsearch.search import Searcher
s = Searcher()
h1 = h3 = 0
for q in qs:
    want = {os.path.join(corpus, p) for p in q["expect"]}
    seen = []
    for cid, fid, k, sc in s._vector(q["q"]):
        if fid not in seen:
            seen.append(fid)
    paths = dict(db.execute(f"SELECT id, path FROM files WHERE id IN ({','.join(map(str, seen[:50]))})"))
    files = [paths[f] for f in seen[:50] if f in paths and not paths[f].endswith(".app")]
    r = next((i + 1 for i, p in enumerate(files) if p in want), None)
    h1 += r == 1; h3 += bool(r and r <= 3)
print(json.dumps({"tag": tag, "load_s": round(load_s, 1), "model_rss_mb": round((rss_model - rss0) / 2**20),
    "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20),
    "chunks_per_s": round(thr, 1), "avg_chunk_chars": round(avg_chars),
    "query_ms_median": round(statistics.median(lat), 1), "query_ms_p90": round(sorted(lat)[int(len(lat)*.9)], 1),
    "vec_only_hit1": h1, "vec_only_hit3": h3}))
