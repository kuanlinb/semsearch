# EmbeddingGemma 2 vs bge-m3

Measured on an M4 Mac (busy with other jobs, so speeds are rough). The prototype in
`semsearch/embed.py` loads `google/embeddinggemma-2` when config `"model"` names it: bfloat16 on
the GPU (float16 overflows), text encoder only, query prompt `task: search result | query: `,
content chunks as `title: <file name> | text: <chunk>`. Loading it also needs `torchvision`.

## Text: look-alike set (76 questions, no reranker)

| Kind | bge-m3 Hit@1 / @3 | Gemma, `title: none` | Gemma, `title: <file name>` |
|---|---|---|---|
| Content only (18) | 17 / 17 | 13 / 17 | 15 / 17 |
| Chinese → English (12) | 5 / 8 | 4 / 8 | 4 / 7 |
| English → Chinese (15) | 9 / 13 | 12 / 15 | 11 / 15 |
| Chinese → Chinese (5) | 5 / 5 | 5 / 5 | 5 / 5 |
| Exact strings (9) | 9 / 9 | 9 / 9 | 9 / 9 |
| OCR (12) | 12 / 12 | 9 / 12 | 10 / 11 |
| File type (3) | 2 / 3 | 2 / 3 | 3 / 3 |
| File name (2) | 2 / 2 | 2 / 2 | 2 / 2 |
| **All** | **61 / 69** | 56 / 71 | 59 / 69 |
| MRR | 0.867 | 0.834 | 0.854 |
| Vectors only (no keywords) Hit@1 / @3 | 61 / 65 | – | 59 / 62 |
| Query vector, median | 19–22 ms | – | 30–43 ms |
| Search, median | 20 ms | 42 ms | 42 ms |
| Search process peak memory | 930 MB | 1256 MB | 1256 MB |
| Download | 2.2 GB | 1.49 GB (one file, all encoders) | |
| Vector size | 1024 | 768 | |

`demo/` with `eval/queries.example.json`: both 5/5.

## Images

The image encoder runs from Python (sentence-transformers 6.2, transformers 5.20, torchvision
0.29). One image on the GPU in bfloat16: 1.5–1.9 s at the default 280 image tokens, 0.16–0.47 s
at 70 tokens; CPU float32 at 280 tokens: 2.9 s. Text + image encoders loaded next to bge-m3 add
about 0.8 GB. On 32 macOS wallpaper thumbnails and three drawn images (a bill screenshot, a bar
chart, a red square), English questions found the right image first 9/9 times at 280 tokens and
8/9 at 70; Chinese questions about 6/9. Unrelated images still score about 0.6, so an image
list needs a cut-off.

## Scripts

    kinds.py <tag> <tag>…       Hit@1/@3 per question kind from eval/lookalike/results
    bench.py <tag> <corpus>     model speed, memory, vectors-only accuracy on an eval index
    imgtest.py <dir> mps [70]   image encoder speed and text → image matches (images in <dir>/imgs)
    imgtime.py <dir> <device> <dtype> <tokens>   time per image
    both.py                     memory and query time with bge-m3 and Gemma loaded together

## llama.cpp: EmbeddingGemma 2 GGUF (Q8_0) for text and photos

`llama-server` from Homebrew (`brew install llama.cpp`, 0.7.0) with `embeddinggemma-2-Q8_0.gguf`
(310 MB) and `mmproj-embeddinggemma-2-Q8_0.gguf` (555 MB) from ggml-org/embeddinggemma-2-GGUF; the
command is in `semsearch/imagevec.py`. Text vectors match PyTorch (cos 1.00), image vectors are
close (cos 0.96-0.99). One photo takes 0.2-0.55 s against 1.5-1.9 s in PyTorch.

Test set: the look-alike corpus plus 29 photos (macOS wallpaper thumbnails renamed
`IMG_8001.jpg`…, so only what they show can find them) and 38 questions about them, 19 English
and 19 Chinese (`queries_photos.json`; many are near-identical seascapes).

| | Text Hit@1 / @3 (76) | Photos Hit@1 / @3 (38) | Search median |
|---|---|---|---|
| bge-m3, no image search | 59 / 69 | 0 / 0 | 44 ms |
| A: bge-m3 + Gemma image list (RRF weight 1) | 58 / 68 | 0 / 0 | 66 ms |
| A: weight 3 | 28 / 45 | 28 / 38 | 66 ms |
| A: weight 3, z-gate 2.7 | 52 / 66 | 21 / 23 | |
| B: Gemma GGUF for text, no images | 56 / 69 | 0 / 0 | 14 ms |
| **B: Gemma GGUF for text and photos, one space** | **58 / 67** | **33 / 37** | 12 ms |

Among images alone the right photo ranks first 35/38 times and in the top three 38/38. With a
separate image list (A) photos only surface when the list outweighs the text lists, and then
photos crowd out documents. In one space (B) a photo competes with text chunks on similarity
directly, and no tuning was needed (offset 0).

Memory: llama-server 760-970 MB with both encoders loaded; the search process with B 49 MB,
with bge-m3 about 920 MB. Speed, interleaved on a busy machine: text chunks 6-17/s for both,
query vector 24 ms (Gemma GGUF) vs 37 ms (bge-m3).

    image_scores.py <corpus>   image-only ranks, top scores and z-scores per question type
    summary.py <tag>…          text and photo Hit@1/@3 from eval/lookalike/results
    speed.py <index.db>        bge-m3 vs llama-server speed, interleaved

## Real photos: Crossmodal-3600

`make_xm3600.py` adds 500 random Crossmodal-3600 photos (Open Images, 100 per folder, named
`IMG_9001.jpg`…) to the look-alike corpus and asks about 100 of them with one human-written
Chinese caption (converted to Traditional Chinese) and one English caption each.

| | Text Hit@1 / @3 (76) | Photos, Chinese (100) | Photos, English (100) |
|---|---|---|---|
| bge-m3, no image search | 61 / 69 | 1 / 1 | 0 / 0 |
| B, offset 0 | 57 / 69 | 48 / 77 | 68 / 87 |
| **B, offset 0.03** | **57 / 68** | **57 / 82** | **69 / 89** |
| B, offset 0.06 | 54 / 66 | 61 / 83 | 69 / 90 |

Among images alone the right photo is first 160/200 and in the top three 185/200. In the full
search, misses at first place lose about half to look-alike photos and half to text files (some
fair: "Books in display" → a reading list). Text losses against bge-m3 are content-only (16 → 12)
and Chinese question / English file (6 → 4); English question / Chinese file gains (9 → 12).

Photos took 0.8 s each here (Open Images photos are about 1024 px): 500 in 7 minutes. A folder
with over 150 serially named files (`IMG_0001.jpg`…) is treated as a dataset and only the folder
is indexed, so camera folders would need an exception for image search.

## C: bge-m3 for text plus a Gemma list (text and photos)

Config `"gemma_channel": true, "image_search": true` with bge-m3 as the model: every chunk also
gets an EmbeddingGemma vector (table `gemma_vecs`), and search adds one more RRF list, each file's
best Gemma similarity with the images ranked in it. A photo has no bge-m3 vectors or keywords, so
when it beats every text chunk in the Gemma space its rank there counts 6 times (`IMAGE_MULT`).
Without that gate, any multiplier that surfaces photos pushes documents down (text 49-57).

Crossmodal-3600 set (where the multiplier and offset were picked):

| | Text (76) | Photos, Chinese (100) | Photos, English (100) |
|---|---|---|---|
| bge-m3 | 61 / 69 | 1 / 1 | 0 / 0 |
| B, offset 0.03 | 57 / 68 | 57 / 82 | 69 / 89 |
| C, no photo gate | 62 / 70 | 1 / 1 | 2 / 2 |
| **C, ×6 when the photo wins, offset 0** | **62 / 70** | 66 / 71 | 68 / 83 |
| C, ×6, offset 0.03 | 60 / 68 | 74 / 90 | 68 / 89 |

Wallpaper set (not used for picking): bge-m3 59/69 text; B 58/67 text, 33/37 photos;
C ×6 offset 0 60/70 text, 34/36 photos; offset 0.03 59/68, 33/37.

C costs both models: about 1.7 GB of memory (bge-m3 920 MB + llama-server 760-970 MB), every
chunk embedded twice, search median 44-72 ms.
