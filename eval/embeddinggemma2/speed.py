"""Interleaved speed test: bge-m3 (PyTorch, Apple GPU) vs EmbeddingGemma 2 GGUF (llama-server).

    python eval/embeddinggemma2/speed.py <index.db with content chunks>
"""
import os, sys, time, sqlite3, statistics, glob
sys.path.insert(0, os.getcwd())
import numpy as np
from sentence_transformers import SentenceTransformer
from semsearch import imagevec
db = sqlite3.connect(sys.argv[1])
texts = [r[0] for r in db.execute("SELECT text FROM chunks WHERE kind=1 ORDER BY length(text) DESC LIMIT 128")]
long_ = [("這是一段比較長的測試內容 used to measure throughput on mixed text. " * 12)[:450] + str(i) for i in range(128)]
b = SentenceTransformer("BAAI/bge-m3", device="mps"); b.max_seq_length = 256; b.half(); b.encode(texts[:8])
def bge(xs): b.encode(xs, batch_size=64)
def gem(xs):
    for i in range(0, len(xs), 32):
        imagevec.embed_texts(["title: x | text: " + x for x in xs[i:i + 32]])
gem(texts[:8])
for rnd in range(2):
    for name, xs in (("corpus chunks", texts), ("450-char chunks", long_)):
        for model, f in (("bge-m3", bge), ("gemma-gguf", gem)):
            t = time.time(); f(xs); print(f"round {rnd} {name:16} {model:11} {len(xs) / (time.time() - t):6.1f} chunks/s")
qs = [f"冰箱壓縮機保固幾年 {i}" for i in range(30)]
for model, f in (("bge-m3", lambda q: b.encode([q])), ("gemma-gguf", lambda q: imagevec.embed_texts([imagevec.QUERY_PROMPT + q]))):
    lat = []
    for q in qs:
        t = time.time(); f(q); lat.append((time.time() - t) * 1000)
    print(f"query vector {model:11} median {statistics.median(lat):.1f} ms")
fs = sorted(glob.glob(os.path.expanduser("~/semsearch-eval-photos/corpus/Photos/*.jpg")))[:12]
lat = []
for f in fs:
    t = time.time(); imagevec.image_vector(f); lat.append((time.time() - t) * 1000)
print(f"photo median {statistics.median(lat):.0f} ms")
