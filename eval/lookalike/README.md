# Look-alike test set

249 fictional personal files where every topic has look-alikes, and 76 questions with known
answers. Search has to find the right file, not just the right topic: three leases, three
vehicle policies, 18 months of utility bills, four flights, two beef noodle soups, four warranty
cards whose compressors are covered for different years, 24 weekly meeting notes, 70 loose notes.

`make_corpus.py` writes the files from a fixed seed, so every run gets the same ones: txt, md,
docx, xlsx, pptx, PDFs with a text layer, and scanned PDFs and screenshots that only OCR can read
(build `bin/semsearch-ocr` first, as `install.sh` does). Everything in it is made up.

The questions (`queries.json`) were written before SemSearch was run on the corpus:

| Kind | Questions | Example |
|---|---|---|
| Content only | 18 | "what was the excess on my old car policy" |
| Chinese question, English file | 12 | 「去成田的回程班機幾點」 |
| English question, Chinese file | 15 | "fridge compressor warranty" |
| Chinese question, Chinese file | 5 | 「車位遙控器遺失要賠多少」 |
| Exact strings | 9 | `58210377`, `NT$18,600`, `B2-17` |
| OCR (screenshots, scans) | 12 | 「房屋稅繳款期限」 |
| File type | 3 | "pricing slides" |
| File name | 2 | 「鳳梨酥」 |

## Results

bge-m3 on an M4 Mac. Hit@1: the right file is the first result; Hit@3: in the first three.

| Kind | bge-m3 Hit@1 / @3 | + bge-reranker-v2-m3 |
|---|---|---|
| Content only | 16 / 17 | 17 / 17 |
| Chinese → English | 6 / 8 | 9 / 11 |
| English → Chinese | 9 / 13 | 14 / 15 |
| Chinese → Chinese | 5 / 5 | 5 / 5 |
| Exact strings | 9 / 9 | 9 / 9 |
| OCR | 12 / 12 | 12 / 12 |
| File type | 2 / 3 | 2 / 3 |
| File name | 2 / 2 | 2 / 2 |
| **All** | **61 / 69** of 76 | **70 / 74** |
| Search time (median) | 27 ms | 2.2 s |

Before 0.1.2, numbers and codes such as `58210377` or `1,718` ranked 13th to 20th: only the right
file contained them, but it got one keyword rank against two vector ranks for unrelated files.
Such lookups now weigh keywords 3× and vectors 0.5× (`is_lookup` in `semsearch/search.py`), which
brought all three to first place and left every other question where it was (58 → 61).

The reranker helps most where look-alikes compete in another language. Two questions are useful
when tuning the cut-offs in `_tiers()`: the right files for 「舊房子的押金退了沒」 and
「單一登入誰負責」 sit close to them, and tighter cut-offs (4.5 / -7.5) hid both.

## Run it

```bash
.venv/bin/python eval/lookalike/make_corpus.py ~/semsearch-lookalike
nice -n 15 .venv/bin/python eval/lookalike/run.py --corpus ~/semsearch-lookalike --tag bge-m3 --reindex
nice -n 15 .venv/bin/python eval/lookalike/run.py --corpus ~/semsearch-lookalike --tag bge-m3_reranker \
    --reranker BAAI/bge-reranker-v2-m3 --reindex
```

Each run writes `results/<tag>.json` with every question's rank, the panel's rank (same-folder
grouping on) and the search time. Keep the corpus outside folders listed in `names_only_roots`.
