"""Text → vectors. The model is loaded once; e5 models need "query: " / "passage: " prefixes."""
import os
import re
import threading

import numpy as np

from . import config

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_model = None
_lock = threading.Lock()
_name = None


def get_model(name: str):
    global _model, _name
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            device = config.device()
            _model = SentenceTransformer(name, device=device)
            _model.max_seq_length = 256
            if device == "mps":
                _model.half()  # ~50% faster on MPS; vectors are stored as float16 anyway
            _name = name
    return _model


def reset():
    global _model, _name
    with _lock:
        _model, _name = None, None


def _prefix(kind: str) -> str:
    if _name and "qwen3-embedding" in _name.lower():
        return ("Instruct: Given a search query, retrieve the user's file that matches it\nQuery: "
                if kind == "query" else "")
    if _name and "e5" in _name.lower():
        return "query: " if kind == "query" else "passage: "
    if _name and "bge" in _name.lower() and "m3" not in _name.lower() and kind == "query":
        return "為這個句子生成表示以用於檢索相關文章："  # bge-*-zh query instruction
    return ""


def encode(texts, kind="passage", batch_size=64) -> np.ndarray:
    m = get_model(_name or "intfloat/multilingual-e5-small")
    p = _prefix(kind)
    vecs = m.encode([p + t for t in texts], batch_size=batch_size,
                    normalize_embeddings=True, convert_to_numpy=True,
                    show_progress_bar=False)
    return vecs.astype(np.float16)


def readable_name(name: str) -> str:
    """Turn names like HW3_final-report.v2 into something closer to a phrase."""
    stem = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", name)
    stem = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)
    stem = re.sub(r"[_\-\.\+]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip() or name
