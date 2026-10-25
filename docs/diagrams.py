"""Generate the README diagrams (light and dark SVG variants).

    python docs/diagrams.py

Writes docs/architecture-{light,dark}.svg and docs/search-flow-{light,dark}.svg.
"""
from pathlib import Path

OUT = Path(__file__).parent
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

THEMES = {
    "light": dict(text="#1f2328", sub="#59636e", box="#ffffff", line="#d0d7de", zone="#f6f8fa",
                  zoneLine="#d0d7de", accent="#0969da", accentFill="#ddf4ff", arrow="#59636e", opt="#8c959f"),
    "dark": dict(text="#e6edf3", sub="#9198a1", box="#151b23", line="#3d444d", zone="#0d1117",
                 zoneLine="#3d444d", accent="#4493f8", accentFill="#0c2d6b", arrow="#9198a1", opt="#6e7681"),
}


def svg(w, h, body, c, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{label}" font-family="{FONT}">\n'
            f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c["arrow"]}"/></marker>'
            f'<marker id="o" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c["opt"]}"/></marker></defs>\n'
            f'{body}</svg>\n')


def box(c, x, y, w, h, title, sub="", accent=False, dashed=False):
    stroke = c["accent"] if accent else (c["opt"] if dashed else c["line"])
    fill = c["accentFill"] if accent else c["box"]
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}/>'
    ty = y + h / 2 + (-4 if sub else 5)
    s += f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" font-size="15" font-weight="600" fill="{c["text"]}">{title}</text>'
    if sub:
        s += f'<text x="{x + w / 2}" y="{ty + 20}" text-anchor="middle" font-size="12.5" fill="{c["sub"]}">{sub}</text>'
    return s + "\n"


def arrow(c, pts, label="", lx=None, ly=None, opt=False, both=False, anchor="middle"):
    col = c["opt"] if opt else c["arrow"]
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    dash = ' stroke-dasharray="6 5"' if opt else ""
    m = "o" if opt else "a"
    start = f' marker-start="url(#{m})"' if both else ""
    s = f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.5"{dash}{start} marker-end="url(#{m})"/>'
    if label:
        s += f'<text x="{lx}" y="{ly}" text-anchor="{anchor}" font-size="12" fill="{c["sub"]}">{label}</text>'
    return s + "\n"


def architecture(c):
    W, H = 1200, 640
    X = [80, 350, 620, 890]          # four columns
    BW, BH = 230, 74
    Y1, Y2 = 128, 352                # indexing lane, search lane
    b = ""
    # boundary: everything inside runs on the user's Mac
    b += f'<rect x="40" y="40" width="1120" height="438" rx="16" fill="{c["zone"]}" stroke="{c["zoneLine"]}" stroke-width="1.5"/>\n'
    b += f'<text x="64" y="72" font-size="14" font-weight="700" fill="{c["text"]}">Runs entirely on your Mac</text>\n'
    b += f'<text x="1136" y="72" text-anchor="end" font-size="12.5" fill="{c["sub"]}">files and queries never leave the machine</text>\n'
    # lane titles
    b += f'<text x="{X[0]}" y="{Y1 - 16}" font-size="12" font-weight="700" letter-spacing="1" fill="{c["sub"]}">INDEXING · IN THE BACKGROUND</text>\n'
    b += f'<text x="{X[0]}" y="{Y2 - 16}" font-size="12" font-weight="700" letter-spacing="1" fill="{c["sub"]}">SEARCH · ON EVERY KEYSTROKE</text>\n'
    # indexing lane
    b += box(c, X[0], Y1, BW, BH, "Your folders", "new files picked up in ~30 s")
    b += box(c, X[1], Y1, BW, BH, "Extract text", "PDF · Office · OCR for images")
    b += box(c, X[2], Y1, BW, BH, "Chunk + embed", "bge-m3 on the Apple GPU")
    b += box(c, X[3], Y1, BW, BH, "SQLite index", "vectors · names · FTS5")
    for i in range(3):
        b += arrow(c, [(X[i] + BW, Y1 + BH / 2), (X[i + 1] - 4, Y1 + BH / 2)])
    # search lane
    b += box(c, X[0], Y2, BW, BH, "⌥Space panel", "Swift menu-bar app", accent=True)
    b += box(c, X[1], Y2, BW, BH, "Embed the query", "same bge-m3 model")
    b += box(c, X[2], Y2, BW, BH, "Hybrid retrieval", "names · content · keywords")
    b += box(c, X[3], Y2, BW, BH, "Rank + group", "rules · usage · same folder")
    for i in range(3):
        b += arrow(c, [(X[i] + BW, Y2 + BH / 2), (X[i + 1] - 4, Y2 + BH / 2)])
    # the index feeds retrieval
    b += arrow(c, [(X[3] + 40, Y1 + BH), (X[3] + 40, Y1 + BH + 40), (X[2] + BW / 2, Y1 + BH + 40), (X[2] + BW / 2, Y2 - 4)],
               "reads vectors + keywords", X[2] + BW / 2 + 12, Y1 + BH + 34, anchor="start")
    # results go back to the panel
    yb = Y2 + BH + 36
    b += arrow(c, [(X[3] + BW / 2, Y2 + BH), (X[3] + BW / 2, yb), (X[0] + BW / 2, yb), (X[0] + BW / 2, Y2 + BH + 4)],
               "results in ~0.1 s", (X[0] + X[3] + BW) / 2, yb - 8)
    # optional reranker on another machine
    RY = 520
    b += box(c, X[3], RY, BW, BH, "Reranker (optional)", "a GPU machine over SSH", dashed=True)
    b += arrow(c, [(X[3] + BW - 40, Y2 + BH), (X[3] + BW - 40, RY - 4)], "top 40", X[3] + BW - 30, RY - 46,
               opt=True, both=True, anchor="start")
    b += f'<text x="{X[3] - 16}" y="{RY + BH / 2 + 5}" text-anchor="end" font-size="12.5" fill="{c["sub"]}">' \
         f'only if you turn it on; falls back to local ranking when unreachable</text>\n'
    return svg(W, H, b, c, "SemSearch architecture: indexing and search both run on your Mac; an optional reranker can run on a GPU machine")


def search_flow(c):
    W, H = 1320, 300
    b = ""
    # query fans out to three retrieval channels, then a single ranking path
    b += box(c, 30, 113, 120, 64, "Query", "", accent=True)
    chans = [("File names", "vector match", 40), ("Contents", "vector match", 113), ("Keywords", "names + FTS5", 186)]
    for t, s, y in chans:
        b += box(c, 200, y, 170, 64, t, s)
        b += arrow(c, [(150, 145), (175, 145), (175, y + 32), (196, y + 32)])
        b += arrow(c, [(370, y + 32), (392, y + 32), (392, 145), (412, 145)])
    steps = [("Fuse", "reciprocal rank"), ("Rules", "type · app · place"), ("Boost", "files you open"),
             ("Rerank", "optional"), ("Group", "same folder")]
    x = 416
    for i, (t, s) in enumerate(steps):
        b += box(c, x, 113, 128, 64, t, s, dashed=(t == "Rerank"))
        b += f'<circle cx="{x + 64}" cy="88" r="11" fill="none" stroke="{c["line"]}" stroke-width="1.5"/>'
        b += f'<text x="{x + 64}" y="92.5" text-anchor="middle" font-size="12" font-weight="700" fill="{c["sub"]}">{i + 1}</text>\n'
        nx = x + 128 + 26
        b += arrow(c, [(x + 128, 145), (nx - 4, 145)])
        x = nx
    b += box(c, x, 113, 104, 64, "Results", "", accent=True)
    b += f'<text x="660" y="282" text-anchor="middle" font-size="12.5" fill="{c["sub"]}">' \
         f'Three ways of matching catch different misses; the steps after the fusion only reorder, they never drop a match.</text>\n'
    return svg(W, H, b, c, "Each search matches file names, contents and keywords, fuses the three lists, then reorders them")


for name, c in THEMES.items():
    (OUT / f"architecture-{name}.svg").write_text(architecture(c))
    (OUT / f"search-flow-{name}.svg").write_text(search_flow(c))
print("ok")
