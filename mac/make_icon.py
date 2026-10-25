"""Draw the app icon: indigo-to-blue rounded square, white magnifier, sparkles ("understands meaning").

Usage: python mac/make_icon.py mac/AppIcon  → AppIcon.icns
"""
import math, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFilter
S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
grad = Image.new("RGBA", (S, S))
top, bot = (94, 92, 230), (10, 132, 255)
px = grad.load()
for y in range(S):
    for x in range(S):
        t = (x + y) / (2 * S)
        px[x, y] = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)) + (255,)
mask = Image.new("L", (S, S), 0)
m = 100
ImageDraw.Draw(mask).rounded_rectangle((m, m, S - m, S - m), radius=185, fill=255)
img.paste(grad, (0, 0), mask)
# soft highlight at the top
hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
hp = hl.load()
for y in range(m, S // 2 + 80):
    alpha = int(52 * max(0.0, 1 - (y - m) / (S // 2 + 80 - m)) ** 1.6)
    for x in range(S):
        hp[x, y] = (255, 255, 255, alpha)
img = Image.alpha_composite(img, Image.composite(hl, Image.new("RGBA", (S, S)), mask))
d = ImageDraw.Draw(img)
cx, cy, r, w = 455, 455, 175, 58
d.ellipse((cx - r, cy - r, cx + r, cy + r), outline="white", width=w)
a = math.radians(45)
x0, y0 = cx + (r + w / 2 - 8) * math.cos(a), cy + (r + w / 2 - 8) * math.sin(a)
d.line((x0, y0, x0 + 190, y0 + 190), fill="white", width=86)
d.ellipse((x0 + 190 - 43, y0 + 190 - 43, x0 + 190 + 43, y0 + 190 + 43), fill="white")
def star(cx, cy, R, rr):
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        rad = R if i % 2 == 0 else rr
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    d.polygon(pts, fill="white")
star(cx, cy, 92, 22)
star(650, 290, 46, 12)
out = sys.argv[1]
os.makedirs(out + ".iconset", exist_ok=True)
for size in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        img.resize((size * scale,) * 2, Image.LANCZOS).save(f"{out}.iconset/icon_{size}x{size}{'@2x' if scale == 2 else ''}.png")
img.save(out + ".png")
subprocess.run(["iconutil", "-c", "icns", out + ".iconset", "-o", out + ".icns"], check=True)
