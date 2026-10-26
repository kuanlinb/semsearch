"""Image vectors: what a photo shows, from EmbeddingGemma 2 run by llama.cpp's llama-server.

Text, images and audio share one vector space in that model, so a text query vector from it
can be compared with the image vectors directly. The text search keeps its own model.

    llama-server -m embeddinggemma-2-Q8_0.gguf --mmproj mmproj-embeddinggemma-2-Q8_0.gguf \
        --embeddings --host 127.0.0.1 --port 9940 --no-webui -c 8192 -b 8192 -ub 8192 -np 1 \
        --image-max-tokens 140
"""
import base64
import functools
import io
import json
import subprocess
import tempfile
import urllib.request

import numpy as np

from . import config

QUERY_PROMPT = "task: search result | query: "
MAX_SIDE = 896  # the server shrinks images to its token budget anyway; this keeps uploads small


def url():
    return config.load().get("image_url", "http://127.0.0.1:9940")


def _post(path, body, timeout=120):
    req = urllib.request.Request(url() + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


@functools.lru_cache(maxsize=1)
def _marker(base):
    # llama-server picks a random media marker at startup; prompts must use it
    with urllib.request.urlopen(base + "/props", timeout=10) as r:
        return json.loads(r.read())["media_marker"]


def available() -> bool:
    try:
        with urllib.request.urlopen(url() + "/health", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def _norm(v):
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    return v / (np.linalg.norm(v) or 1)


def embed_texts(texts):
    """Vectors for texts that already carry their prompt."""
    r = _post("/v1/embeddings", {"input": list(texts)})
    return np.array([_norm(d["embedding"]) for d in sorted(r["data"], key=lambda d: d["index"])])


@functools.lru_cache(maxsize=64)
def query_vector(q: str) -> np.ndarray:
    return embed_texts([QUERY_PROMPT + q])[0]


def _jpeg(path: str) -> bytes:
    """The image as a JPEG at most MAX_SIDE pixels wide or tall; HEIC goes through sips."""
    from PIL import Image
    try:
        im = Image.open(path)
        im.draft("RGB", (MAX_SIDE, MAX_SIDE))  # JPEG: decode at a reduced size, much faster
        im = im.convert("RGB")
    except Exception:
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
            subprocess.run(["sips", "-s", "format", "jpeg", "-Z", str(MAX_SIDE), path, "--out", tmp.name],
                           capture_output=True, check=True, timeout=60)
            return open(tmp.name, "rb").read()
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def image_vector(path: str) -> np.ndarray:
    data = base64.b64encode(_jpeg(path)).decode()
    r = _post("/embeddings", {"content": [{"prompt_string": _marker(url()), "multimodal_data": [data]}]})
    return _norm(r[0]["embedding"])
