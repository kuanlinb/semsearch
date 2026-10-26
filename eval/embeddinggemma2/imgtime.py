import sys, time, glob, statistics, json, torch
from PIL import Image
from sentence_transformers import SentenceTransformer
SP, dev, dt, tok = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
m = SentenceTransformer("google/embeddinggemma-2", device=dev, model_kwargs={"dtype": getattr(torch, dt)},
                        config_kwargs={"audio_config": None})
proc = m[0].processor
if tok != 280:
    proc.image_processor.max_soft_tokens = tok; proc.image_processor.image_seq_length = tok
    proc.image_seq_length = tok
imgs = [Image.open(f).convert("RGB") for f in sorted(glob.glob(f"{SP}/imgs/*"))][:12]
ref = m.encode(imgs[:2], normalize_embeddings=True)
t = time.time(); [proc.image_processor(im) for im in imgs]; pre = (time.time() - t) * 1000 / len(imgs)
one = []
for im in imgs:
    t = time.time(); m.encode([im]); one.append((time.time() - t) * 1000)
print(json.dumps({"dev": dev, "dtype": dt, "soft_tokens": tok, "preprocess_ms": round(pre), "img_ms_median": round(statistics.median(one)),
                  "threads": torch.get_num_threads()}))
