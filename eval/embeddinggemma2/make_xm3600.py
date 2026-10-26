"""Photo test set from Crossmodal-3600 (Thapliyal et al. 2022): 3600 Open Images photos, each with
human-written captions in 36 languages. Captions CC BY 4.0, images CC BY 2.0 (Open Images).

    curl -LO https://open-images-dataset.s3.amazonaws.com/crossmodal-3600/images.tgz
    curl -LO https://google.github.io/crossmodal-3600/web-data/captions.zip
    (unpack into <dl>/img and <dl>/cap)
    python eval/embeddinggemma2/make_xm3600.py <dl> <corpus made by eval/lookalike/make_corpus.py> <out>

Copies <corpus> to <out>/corpus, adds 500 random photos as Photos/2025-01/IMG_9001.jpg … (names say nothing
about content), and writes <out>/queries.json: the 76 look-alike questions plus, for the first 100
photos, one Chinese caption (converted to Traditional Chinese, Taiwan usage, with OpenCC) and one
English caption as questions. The shortest caption is used: closest to what people type.
"""
import json
import os
import random
import shutil
import sys

from opencc import OpenCC

HERE = os.path.dirname(os.path.abspath(__file__))
N_PHOTOS, N_TARGETS = 500, 100


def main():
    dl, src, out = (os.path.expanduser(a) for a in sys.argv[1:4])
    caps = {}
    for line in open(os.path.join(dl, "cap", "captions.jsonl")):
        r = json.loads(line)
        if r.get("zh", {}).get("caption") and r.get("en", {}).get("caption"):
            caps[r["image/key"]] = (min(r["zh"]["caption"], key=len), min(r["en"]["caption"], key=len))
    keys = sorted(k for k in caps if os.path.exists(os.path.join(dl, "img", k + ".jpg")))
    picked = random.Random(3600).sample(keys, N_PHOTOS)
    shutil.rmtree(os.path.join(out, "corpus"), ignore_errors=True)
    shutil.copytree(src, os.path.join(out, "corpus"))
    s2tw = OpenCC("s2twp")
    qs = json.load(open(os.path.join(os.path.dirname(HERE), "lookalike", "queries.json")))["queries"]
    keymap = {}
    for i, k in enumerate(picked):
        # 100 per folder: a folder with over 150 serially named files counts as a dataset
        # (config.DATASET_THRESHOLD) and only the folder itself would be indexed
        name = f"Photos/2025-{i // 100 + 1:02d}/IMG_{9001 + i}.jpg"
        os.makedirs(os.path.dirname(os.path.join(out, "corpus", name)), exist_ok=True)
        shutil.copy(os.path.join(dl, "img", k + ".jpg"), os.path.join(out, "corpus", name))
        keymap[name] = k
        if i < N_TARGETS:
            zh, en = caps[k]
            qs.append({"q": s2tw.convert(zh).strip("。. "), "expect": [name], "tag": "photo-zh"})
            qs.append({"q": en.strip(". "), "expect": [name], "tag": "photo-en"})
    json.dump({"about": f"eval/lookalike questions plus {2 * N_TARGETS} Crossmodal-3600 captions as questions "
                        f"about {N_TARGETS} of {N_PHOTOS} photos", "queries": qs, "photos": keymap},
              open(os.path.join(out, "queries.json"), "w"), ensure_ascii=False, indent=1)
    print(len(qs), "questions,", N_PHOTOS, "photos in", out)


if __name__ == "__main__":
    main()
