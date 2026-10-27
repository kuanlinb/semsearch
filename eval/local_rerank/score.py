"""Score collected candidates (collect.py) with a reranker, then replay the ranking for several
"rerank only the top K" settings.

    python eval/local_rerank/score.py <cands.json> --backend onnx --model <dir> [--threads 4] [--tag T]
    python eval/local_rerank/score.py <cands.json> --backend torch [--model BAAI/bge-reranker-v2-m3]

Prints Hit@1 / Hit@3 for K = 0 (no reranker), 5, 10, 20, 40 and the median time to score K texts
for one query; writes the scores next to the input as <cands>.<tag>.json.
"""
import argparse
import json
import statistics
import time

import numpy as np

KS = (5, 10, 20, 40)


class Onnx:
    def __init__(self, d, threads, max_len):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.tok = Tokenizer.from_file(f"{d}/tokenizer.json")
        self.tok.enable_truncation(max_len)
        self.tok.enable_padding(pad_id=self.tok.token_to_id("<pad>") or 1)
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        self.s = ort.InferenceSession(f"{d}/model.onnx", so, providers=["CPUExecutionProvider"])

    def __call__(self, q, texts):
        enc = self.tok.encode_batch([(q, t) for t in texts])
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        return self.s.run(None, {"input_ids": ids, "attention_mask": mask})[0].ravel().tolist()


class Torch:
    def __init__(self, name, max_len, device):
        import torch
        from sentence_transformers import CrossEncoder
        self.torch = torch
        self.ce = CrossEncoder(name, device=device, max_length=max_len)
        if device == "mps":
            self.ce.model.half()

    def __call__(self, q, texts):
        return self.ce.predict([(q, t) for t in texts], batch_size=16, show_progress_bar=False,
                               activation_fn=self.torch.nn.Identity()).tolist()


def hits(rows, scores, k):
    h1 = h3 = 0
    for r, sc in zip(rows, scores):
        order = list(range(len(r["cands"])))
        if k:
            top = sorted(order[:k], key=lambda i: -(sc[i] + (1.0 if r["name_bonus"][i] else 0.0)))
            order = top + order[k:]
        files = [r["cands"][i] for i in order if r["is_file"][i]]
        rank = next((i + 1 for i, c in enumerate(files) if c in r["expect"]), None)
        h1 += rank == 1
        h3 += bool(rank and rank <= 3)
    return h1, h3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cands")
    ap.add_argument("--backend", choices=["onnx", "torch"], required=True)
    ap.add_argument("--model", default="BAAI/bge-reranker-v2-m3")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    rows = json.load(open(a.cands))["queries"]
    m = Onnx(a.model, a.threads, a.max_len) if a.backend == "onnx" else Torch(a.model, a.max_len, a.device)
    m(rows[0]["q"], rows[0]["texts"][:4])  # warm up
    scores = [m(r["q"], r["texts"]) for r in rows]
    times = {}
    for k in (5, 10, 20):
        ts = []
        for r in rows[:30]:
            t = time.perf_counter()
            m(r["q"], r["texts"][:k])
            ts.append(time.perf_counter() - t)
        times[k] = round(statistics.median(ts) * 1000)
    out = {"tag": a.tag, "n": len(rows), "K0": hits(rows, scores, 0)}
    for k in KS:
        out[f"K{k}"] = hits(rows, scores, k)
    out["ms"] = times
    print(json.dumps(out))
    if a.tag:
        json.dump({"summary": out, "scores": scores}, open(a.cands.removesuffix(".json") + f".{a.tag}.json", "w"))


if __name__ == "__main__":
    main()
