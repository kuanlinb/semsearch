"""Text → vectors. The model is loaded once; e5 models need "query: " / "passage: " prefixes,
EmbeddingGemma "task: search result | query: " / "title: … | text: ".

Two runtimes (config "embed_backend"):
  "torch"  sentence-transformers on PyTorch (Apple GPU through MPS), any Hugging Face model
  "onnx"   ONNX Runtime with an int8 export of bge-m3: no PyTorch needed, runs on the CPU (default)
  "llama"  a running llama.cpp llama-server (config "image_url"), e.g. EmbeddingGemma 2 GGUF
"""
import hashlib
import os
import re
import threading
import urllib.request

import numpy as np

from . import config

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_model = None
_lock = threading.Lock()
_name = None


# ONNX exports: model name -> (folder name, where to download, {file: sha256}). bge-m3 is
# quantized per output channel by tools/export_onnx.py (cosine ~0.993 to the PyTorch vectors;
# same Hit@1 / Hit@3 on eval/lookalike). The config key "onnx_model" can instead name a local
# folder with model.onnx, model.onnx_data and tokenizer.json.
ONNX_MODELS = {
    "BAAI/bge-m3": ("bge-m3-onnx-int8", "https://github.com/kuanlinb/semsearch/releases/download/bge-m3-onnx-int8/", {
        "model.onnx": "c63c378174a4352c28bc5d6e9cf0605f13148a385f69363d66266753938277b8",
        "model.onnx_data": "e2cd25b5dd81c0ec6e06a805ea8a4c72634eacb656a7f4cdee6e9dbc062daae8",
        "tokenizer.json": "6710678b12670bc442b99edc952c4d996ae309a7020c1fa0096dd245c2faf790",
    }),
}
MAX_TOKENS = 256


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _ssl_context():
    """Certificates for the download. A python.org Python has none until its "Install
    Certificates" step was run, so macOS's own list (/etc/ssl/cert.pem) is added."""
    import ssl
    ctx = ssl.create_default_context()
    if os.path.exists("/etc/ssl/cert.pem"):
        try:
            ctx.load_verify_locations("/etc/ssl/cert.pem")
        except ssl.SSLError:
            pass
    return ctx


DOWNLOAD_STATUS = "model-download.json"  # in DATA_DIR, read by the app while the service starts


def _report(**state):
    """Download progress for the app ({} removes it): the search service is not answering yet."""
    import json
    path = config.DATA_DIR / DOWNLOAD_STATUS
    try:
        if not state:
            path.unlink(missing_ok=True)
            return
        config.ensure_data_dir()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(path)
    except OSError:
        pass


def _download(url, tmp, label, timeout=60):
    """Append to `tmp` from where an earlier attempt stopped (HTTP Range), reporting progress."""
    import time
    import urllib.error
    have = tmp.stat().st_size if tmp.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    try:
        r = urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:  # already complete
            return
        raise
    with r:
        if have and getattr(r, "status", None) != 206:
            have = 0  # the server sent the whole file again
        total = have + int(r.headers.get("Content-Length") or 0)
        last = 0.0
        with open(tmp, "ab" if have else "wb") as f:
            done = have
            while True:
                block = r.read(1 << 20)
                if not block:
                    break
                f.write(block)
                done += len(block)
                if time.time() - last > 1:
                    _report(file=label, done=done, total=total)
                    last = time.time()
        if total and done < total:
            raise OSError(f"connection closed at {done} of {total} bytes")


def _fetch(folder, url, files, attempts=6):
    """The model's files, downloaded once into config.MODELS_DIR/folder and checked.
    A dropped or stalled connection is retried, continuing where it stopped (the model is
    about 590 MB: starting over on every hiccup can mean it never finishes)."""
    import time
    dest = config.MODELS_DIR / folder
    dest.mkdir(parents=True, exist_ok=True)
    for name, sha in files.items():
        path = dest / name
        if path.exists():
            continue
        tmp = path.with_suffix(path.suffix + ".part")
        print(f"downloading {url}{name}", flush=True)
        for attempt in range(attempts):
            try:
                _download(url + name, tmp, name)
                break
            except OSError as e:  # includes URLError, timeouts and refused connections
                if attempt == attempts - 1:
                    _report(file=name, error=f"{e}")
                    raise RuntimeError(f"could not download {name} ({e}); check the network. "
                                       "The next try continues where this one stopped") from e
                print(f"download of {name} interrupted ({e}); retrying", flush=True)
                _report(file=name, retrying=f"{e}")
                time.sleep(min(60, 2 ** attempt * 3))
        if _sha256(tmp) != sha:
            tmp.unlink()
            _report(file=name, error="checksum mismatch")
            raise RuntimeError(f"{name} from {url} does not match its checksum; try again later")
        tmp.rename(path)
    _report()
    return dest


class OnnxModel:
    """CLS-pooled, normalized embeddings from an ONNX export (what sentence-transformers does for bge-m3)."""

    def __init__(self, name):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        local = config.load().get("onnx_model")
        if local:
            local = os.path.expanduser(local)
            model_path, tok_path = os.path.join(local, "model.onnx"), os.path.join(local, "tokenizer.json")
        elif name in ONNX_MODELS:
            folder = _fetch(*ONNX_MODELS[name])
            model_path, tok_path = str(folder / "model.onnx"), str(folder / "tokenizer.json")
        else:
            raise ValueError(f"no ONNX export known for {name}; use embed_backend \"torch\"")
        self.tok = Tokenizer.from_file(tok_path)
        self.tok.enable_truncation(MAX_TOKENS)
        self.tok.enable_padding(pad_id=self.tok.token_to_id("<pad>") or 0)
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # Weights in a separate model.onnx_data file are memory-mapped instead of copied; without
        # the arena, memory used for a batch is given back afterwards
        so.enable_cpu_mem_arena = False
        # Leave cores free for whatever else is running
        so.intra_op_num_threads = int(os.environ.get("SEMSEARCH_THREADS", max(1, (os.cpu_count() or 4) // 2)))
        self.sess = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}

    def encode(self, texts, batch_size=8):
        out = np.empty((len(texts), 0), np.float32)
        order = np.argsort([-len(t) for t in texts], kind="stable")  # similar lengths → little padding
        parts = []
        for i in range(0, len(texts), batch_size):
            enc = self.tok.encode_batch([texts[j] for j in order[i:i + batch_size]])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            cls = self.sess.run(None, feed)[0][:, 0].astype(np.float32)
            parts.append(cls / np.linalg.norm(cls, axis=1, keepdims=True))
        if parts:
            out = np.empty((len(texts), parts[0].shape[1]), np.float32)
            out[order] = np.concatenate(parts)
        return out


class LlamaModel:
    """Embeddings from llama-server (see semsearch/imagevec.py for the command)."""

    def encode(self, texts, batch_size=32):
        from . import imagevec
        if len(texts) == 1 and texts[0].startswith(imagevec.QUERY_PROMPT):
            # a search query: the image list asks for the same vector, so it is cached there
            return imagevec.query_vector(texts[0][len(imagevec.QUERY_PROMPT):])[None]
        parts = [imagevec.embed_texts(texts[i:i + batch_size]) for i in range(0, len(texts), batch_size)]
        return np.concatenate(parts) if parts else np.empty((0, 768), np.float32)
class OnnxReranker:
    """A cross-encoder (bge-reranker-v2-m3) exported by eval/local_rerank/export_reranker.py and
    quantized by tools/export_onnx.py: raw logits, the scale the tier cut-offs use. CPU only."""

    def __init__(self, folder, max_tokens=256):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        folder = os.path.expanduser(folder)
        self.tok = Tokenizer.from_file(os.path.join(folder, "tokenizer.json"))
        self.tok.enable_truncation(max_tokens)
        self.tok.enable_padding(pad_id=self.tok.token_to_id("<pad>") or 1)
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.enable_cpu_mem_arena = False
        so.intra_op_num_threads = int(os.environ.get("SEMSEARCH_THREADS", max(1, (os.cpu_count() or 4) // 2)))
        self.sess = ort.InferenceSession(os.path.join(folder, "model.onnx"), so, providers=["CPUExecutionProvider"])

    def scores(self, q, texts, batch_size=8):
        out = []
        for i in range(0, len(texts), batch_size):
            enc = self.tok.encode_batch([(q, t) for t in texts[i:i + batch_size]])
            feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                    "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
            out.extend(self.sess.run(None, feed)[0].ravel().tolist())
        return out


def get_model(name: str):
    global _model, _name
    with _lock:
        if _model is None and config.embed_backend() == "llama":
            _model, _name = LlamaModel(), name
        if _model is None and config.embed_backend() == "onnx":
            _model, _name = OnnxModel(name), name
        if _model is None:
            from sentence_transformers import SentenceTransformer
            device = config.device()
            if _is_gemma(name):
                # EmbeddingGemma 2 overflows float16 (NaN or silently worse vectors): bfloat16 on the
                # GPU, and only the text encoder (the image and audio encoders add ~470M parameters)
                import torch
                _model = SentenceTransformer(
                    name, device=device,
                    model_kwargs={"dtype": torch.bfloat16 if device == "mps" else torch.float32},
                    config_kwargs={"vision_config": None, "audio_config": None})
            else:
                local = _fp16_copy(name) if device == "mps" else None
                if local:
                    import torch
                    _model = SentenceTransformer(local, device=device, model_kwargs={"dtype": torch.float16})
                else:
                    _model = SentenceTransformer(name, device=device)
                    if device == "mps":
                        _model.half()  # ~50% faster on MPS; vectors are stored as float16 anyway
            _model.max_seq_length = MAX_TOKENS
            _name = name
    return _model


def _fp16_copy(name: str):
    """A float16 safetensors copy of the model, made the first time and reused after that.

    bge-m3 ships as a float32 pytorch_model.bin: loading it reads the whole file into memory and
    converts it, and that CPU copy stays behind after the model moves to the GPU (~1.1 GB per
    process). A float16 safetensors file is memory-mapped instead (2.8 GB → 1.7 GB for bge-m3,
    identical vectors). The conversion runs in a child process, so its memory goes away with it.
    """
    import shutil
    import subprocess
    import sys
    dst = config.DATA_DIR / "models" / (name.replace("/", "--") + "-fp16")
    if (dst / "model.safetensors").exists():
        return str(dst)
    tmp = dst.with_name(dst.name + f".tmp{os.getpid()}")
    code = ("import sys, torch\n"
            "from sentence_transformers import SentenceTransformer\n"
            "m = SentenceTransformer(sys.argv[1], device='cpu', model_kwargs={'dtype': torch.float16})\n"
            "m.save(sys.argv[2], safe_serialization=True)\n")
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-c", code, name, str(tmp)], check=True, timeout=900,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            os.rename(tmp, dst)
        except OSError:  # the server or the indexer made it first
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
    return str(dst) if (dst / "model.safetensors").exists() else None


def release_gpu_cache():
    """Give PyTorch's cached MPS memory back to the system; a long-running process keeps growing
    otherwise. Does nothing (and never imports torch) on the ONNX and llama backends."""
    import sys
    torch = sys.modules.get("torch")
    if torch is None:
        return
    try:
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except Exception:
        pass


def reset():
    global _model, _name
    with _lock:
        _model, _name = None, None


def _is_gemma(name) -> bool:
    return bool(name) and "embeddinggemma" in name.lower()


def _prefix(kind: str) -> str:
    if _is_gemma(_name):
        return "task: search result | query: " if kind == "query" else "title: none | text: "
    if _name and "qwen3-embedding" in _name.lower():
        return ("Instruct: Given a search query, retrieve the user's file that matches it\nQuery: "
                if kind == "query" else "")
    if _name and "e5" in _name.lower():
        return "query: " if kind == "query" else "passage: "
    if _name and "bge" in _name.lower() and "m3" not in _name.lower() and kind == "query":
        return "為這個句子生成表示以用於檢索相關文章："  # bge-*-zh query instruction
    return ""


def content_text(title: str, text: str) -> str:
    """A content chunk as it is embedded: the file's readable name, then the text."""
    if _is_gemma(_name):
        return f"title: {title} | text: {text}"  # EmbeddingGemma's format for titled documents
    return f"{title}: {text}"


def encode(texts, kind="passage", batch_size=64) -> np.ndarray:
    m = get_model(_name or "intfloat/multilingual-e5-small")
    p = _prefix(kind)
    if p and kind != "query" and _is_gemma(_name):
        # chunks already in "title: … | text: …" form keep their own title
        return _encode(m, [t if t.startswith("title: ") else p + t for t in texts], batch_size)
    return _encode(m, [p + t for t in texts], batch_size)


def _encode(m, texts, batch_size):
    if isinstance(m, (OnnxModel, LlamaModel)):
        return m.encode(texts).astype(np.float16)
    vecs = m.encode(texts, batch_size=batch_size,
                    normalize_embeddings=True, convert_to_numpy=True,
                    show_progress_bar=False)
    return vecs.astype(np.float16)


def readable_name(name: str) -> str:
    """Turn names like HW3_final-report.v2 into something closer to a phrase."""
    stem = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", name)
    stem = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)
    stem = re.sub(r"[_\-\.\+]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip() or name
