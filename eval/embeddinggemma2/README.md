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
