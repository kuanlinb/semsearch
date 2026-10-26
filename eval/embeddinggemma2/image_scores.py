"""Top image score per question, and where the right photo ranks among images only.

    SEMSEARCH_DATA=~/.semsearch_eval/<tag> python eval/embeddinggemma2/image_scores.py <corpus>
"""
import json, os, sqlite3, sys
import numpy as np
sys.path.insert(0, os.getcwd())
from semsearch import config, imagevec
corpus = sys.argv[1]
QUERIES = sys.argv[2] if len(sys.argv) > 2 else "eval/embeddinggemma2/queries_photos.json"
db = sqlite3.connect(config.DB_PATH)
rows = [(f, p, v) for f, p, v in db.execute("SELECT i.file_id, f.path, i.vec FROM image_vecs i JOIN files f ON f.id=i.file_id") if v]
paths = [os.path.relpath(p, corpus) for _, p, _ in rows]
M = np.array([np.frombuffer(v, np.float16) for _, _, v in rows], np.float32)
out = {"text": [], "photo": []}
for q in json.load(open(QUERIES))["queries"]:
    sc = M @ imagevec.query_vector(q["q"])
    order = np.argsort(-sc)
    kind = "photo" if q["tag"].startswith("photo") else "text"
    rank = next((i + 1 for i, j in enumerate(order) if paths[j] in q["expect"]), None)
    right = max((sc[j] for j in range(len(paths)) if paths[j] in q["expect"]), default=None)
    out[kind].append((float(sc[order[0]]), float(sc[order[0]] - sc[order[1]]), rank, right, q["q"]))
for k, v in out.items():
    tops = sorted(x[0] for x in v)
    print(k, "top score min/median/max", round(tops[0], 3), round(tops[len(tops) // 2], 3), round(tops[-1], 3))
p = out["photo"]
print("photo: right photo rank among images  @1", sum(x[2] == 1 for x in p), "@3", sum(bool(x[2] and x[2] <= 3) for x in p), "of", len(p))
print("photo: right photo score min", round(min(x[3] for x in p), 3))
for x in sorted(out["text"], reverse=True)[:5]: print("  text high", round(x[0], 3), x[4])
for x in sorted(p, key=lambda x: x[3])[:5]: print("  photo low right", round(x[3], 3), x[2], x[4])

# How far the best image stands out from all images (z-score), by question type
print("\nz of the top image:")
groups = {"photo": [], "text, answer is an image": [], "text, answer is not an image": []}
for q in json.load(open(QUERIES))["queries"]:
    sc = M @ imagevec.query_vector(q["q"])
    z = (sc.max() - sc.mean()) / sc.std()
    if q["tag"].startswith("photo"):
        g = "photo"
    elif any(os.path.splitext(e)[1].lower() in config.IMAGE_EXT for e in q["expect"]):
        g = "text, answer is an image"
    else:
        g = "text, answer is not an image"
    groups[g].append((float(z), q["q"]))
for g, v in groups.items():
    zs = sorted(z for z, _ in v)
    print(f"  {g:30} n={len(v):3} z min {zs[0]:.2f}  p10 {zs[len(zs) // 10]:.2f}  median {zs[len(zs) // 2]:.2f}  max {zs[-1]:.2f}")
    print("     ", "  ".join(f"{z:.1f}" for z in zs))
