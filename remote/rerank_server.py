"""Optional remote reranker: scores SemSearch results with a cross-encoder on a GPU machine.

Run it on a machine with a CUDA GPU (or any machine with torch + transformers):

    python rerank_server.py [--port 8798] [--model BAAI/bge-reranker-v2-m3]

It listens on 127.0.0.1 only. The Mac reaches it through an SSH tunnel
(ssh -L 8798:127.0.0.1:8798 my-gpu-box), so file snippets never cross the network in
plain text. The model is loaded on first use and unloaded after 15 idle minutes, so it
does not hold GPU memory while you are not searching.

  POST /rerank  {"query": "...", "texts": ["...", ...]}  ->  {"scores": [...], "ms": 12}
  GET  /health
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_TEXTS = 200
BATCH = 32

_lock = threading.Lock()
_state = {"model": None, "tok": None, "last": 0.0}
_args = None


def _device():
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _tokenizer(model):
    """AutoTokenizer, falling back to tokenizer.json directly: some transformers 5.x
    releases fail to load the sentencepiece vocabulary of XLM-R based rerankers."""
    from transformers import AutoTokenizer
    try:
        return AutoTokenizer.from_pretrained(model)
    except OSError:
        import json
        from huggingface_hub import hf_hub_download
        from transformers import PreTrainedTokenizerFast
        special = json.load(open(hf_hub_download(model, "special_tokens_map.json")))
        special = {k: (v["content"] if isinstance(v, dict) else v) for k, v in special.items()
                   if isinstance(v, (str, dict))}
        return PreTrainedTokenizerFast(tokenizer_file=hf_hub_download(model, "tokenizer.json"), **special)


def _load():
    import torch
    from transformers import AutoModelForSequenceClassification
    if _state["model"] is None:
        dev = _device()
        _state["tok"] = _tokenizer(_args.model)
        dtype = torch.float16 if dev != "cpu" else torch.float32
        m = AutoModelForSequenceClassification.from_pretrained(_args.model, dtype=dtype)
        _state["model"] = m.to(dev).eval()
        _state["dev"] = dev
    _state["last"] = time.time()
    return _state["model"], _state["tok"], _state["dev"]


def score(query, texts):
    import torch
    with _lock:
        model, tok, dev = _load()
        out = []
        for i in range(0, len(texts), BATCH):
            batch = tok([[query, t] for t in texts[i:i + BATCH]], padding=True, truncation=True,
                        max_length=512, return_tensors="pt").to(dev)
            with torch.no_grad():
                out += model(**batch).logits.view(-1).float().cpu().tolist()
        _state["last"] = time.time()
        return out


def _unloader():
    import gc
    while True:
        time.sleep(60)
        with _lock:
            if _state["model"] is not None and time.time() - _state["last"] > _args.idle_minutes * 60:
                import torch
                _state["model"] = _state["tok"] = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _trusted(self):
        """Only answer requests addressed to this loopback port: blocks DNS-rebinding pages."""
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def do_GET(self):
        if not self._trusted():
            return self._send(403, {"error": "forbidden"})
        if self.path == "/health":
            return self._send(200, {"ok": True, "loaded": _state["model"] is not None})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._trusted() or self.path != "/rerank":
            return self._send(403, {"error": "forbidden"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(min(n, 5_000_000)))
            t0 = time.time()
            s = score(str(body["query"]), [str(t) for t in body["texts"]][:MAX_TEXTS])
            self._send(200, {"scores": s, "ms": int((time.time() - t0) * 1000)})
        except Exception as e:
            self._send(500, {"error": str(e)})


def main():
    global _args
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8798)
    ap.add_argument("--model", default="BAAI/bge-reranker-v2-m3")
    ap.add_argument("--idle-minutes", type=float, default=15, help="unload the model after this long unused")
    _args = ap.parse_args()
    threading.Thread(target=_unloader, daemon=True).start()
    print(f"rerank server on http://127.0.0.1:{_args.port} ({_args.model})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", _args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
