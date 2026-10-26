import os, sys, time, glob, statistics, json
import numpy as np, psutil, torch
from PIL import Image, ImageDraw, ImageFont
SP = sys.argv[1]; dev = sys.argv[2] if len(sys.argv) > 2 else "mps"
d = f"{SP}/imgs"
font = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 40)
im = Image.new("RGB", (900, 600), "white"); g = ImageDraw.Draw(im)
g.text((40, 40), "台灣電力公司 電費帳單", fill="black", font=font)
g.text((40, 140), "計費期間 2026/08/01–09/30", fill="black", font=font)
g.text((40, 240), "應繳金額 NT$1,718", fill="red", font=font)
im.save(f"{d}/電費截圖.png")
im = Image.new("RGB", (800, 600), "white"); g = ImageDraw.Draw(im)
for i, h in enumerate([120, 300, 220, 450]):
    g.rectangle([100 + i * 160, 550 - h, 200 + i * 160, 550], fill=["#4472c4", "#ed7d31", "#a5a5a5", "#ffc000"][i])
g.text((100, 20), "Quarterly revenue", fill="black", font=font)
im.save(f"{d}/chart.png")
Image.new("RGB", (400, 400), "#d02020").save(f"{d}/red.png")

from sentence_transformers import SentenceTransformer
p = psutil.Process(); r0 = p.memory_info().rss
t = time.time()
m = SentenceTransformer("google/embeddinggemma-2", device=dev,
                        model_kwargs={"dtype": torch.bfloat16 if dev == "mps" else torch.float32},
                        config_kwargs={"audio_config": None})
load = time.time() - t
if len(sys.argv) > 3:
    ip = m[0].processor.image_processor; ip.max_soft_tokens = ip.image_seq_length = m[0].processor.image_seq_length = int(sys.argv[3])
nparams = sum(x.numel() for x in m.parameters()) / 1e6
files = sorted(glob.glob(f"{d}/*"))
imgs = [Image.open(f).convert("RGB") for f in files]
m.encode(imgs[:2], batch_size=2)
one = []
for im in imgs[:10]:
    t = time.time(); m.encode([im]); one.append((time.time() - t) * 1000)
t = time.time(); iv = m.encode(imgs, batch_size=8, normalize_embeddings=True); batch_ms = (time.time() - t) * 1000 / len(imgs)
print(json.dumps({"device": dev, "load_s": round(load, 1), "params_M": round(nparams), "rss_mb": round((p.memory_info().rss - r0) / 2**20),
                  "img_ms_single_median": round(statistics.median(one)), "img_ms_batched": round(batch_ms), "n_imgs": len(imgs)}))
names = [os.path.basename(f) for f in files]
queries = ["sunset over the ocean", "海邊的夕陽", "a lone tree", "一棵樹", "desert sand dunes", "沙漠",
           "lake with mountains", "湖", "electricity bill amount", "電費多少錢", "bar chart of revenue", "長條圖",
           "solid red", "紅色", "rocky cliffs by the sea", "海邊懸崖", "night sky with plants", "夜晚的植物"]
qv = m.encode(queries, prompt_name="SearchQuery", normalize_embeddings=True)
S = qv @ iv.T
for q, row in zip(queries, S):
    top = np.argsort(-row)[:3]
    print(f"{q:28} → " + " | ".join(f"{names[i][:22]} {row[i]:.2f}" for i in top))
# text vectors from the multimodal load vs the text-only load used for the index
t2 = m.encode(["冰箱壓縮機保固幾年"], prompt_name="SearchQuery", normalize_embeddings=True)
np.save(f"{SP}/q_mm_{dev}.npy", t2)
