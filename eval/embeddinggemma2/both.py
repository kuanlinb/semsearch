import resource, time, torch, psutil, statistics
from sentence_transformers import SentenceTransformer
p = psutil.Process()
def foot(): return round(p.memory_footprint() / 2**20) if hasattr(p, "memory_footprint") else round(p.memory_info().rss / 2**20)
b = SentenceTransformer("BAAI/bge-m3", device="mps"); b.half(); b.encode(["x"])
print("bge-m3 only: rss", round(p.memory_info().rss / 2**20), "MB, mps driver", round(torch.mps.driver_allocated_memory() / 2**20), "MB")
g = SentenceTransformer("google/embeddinggemma-2", device="mps", model_kwargs={"dtype": torch.bfloat16}, config_kwargs={"audio_config": None})
g.encode(["x"], prompt_name="SearchQuery")
print("+ gemma text+vision: rss", round(p.memory_info().rss / 2**20), "MB, mps driver", round(torch.mps.driver_allocated_memory() / 2**20), "MB")
lat = []
for q in ["冰箱壓縮機保固幾年", "beef noodle soup", "海邊的夕陽", "去年夏天在京都拍的照片"] * 5:
    t = time.time(); b.encode([q]); g.encode([q], prompt_name="SearchQuery"); lat.append((time.time() - t) * 1000)
print("both query vectors, median ms", round(statistics.median(lat)))
print("peak rss", round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20), "MB")
