"""Render map.jpg: GTA VI code-locked locations over the gtadb.org map tiles.

Base map: "GTA VI Map Tiles (CC BY 4.0) - https://map.gtadb.org".
Get the tiles without hitting gtadb.org (as its readme asks):

    git clone --depth 1 --filter=blob:none --sparse https://github.com/rolux/gtadb.org
    cd gtadb.org && git sparse-checkout set --no-cone /maps/tiles/6/day/3/

Then:  python3 tools/render_map.py /path/to/gtadb.org

The grid reproduces the 1-9 / A-M grid of the "Visit Leonida" poster map.
It was aligned by cross-correlating land masks (fit scale 0.183 poster
px per metre; every test landmark landed on its poster label).
"""

import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILES = os.path.join(sys.argv[1], "maps/tiles/6/day/3")
OUT = os.path.join(ROOT, "map.jpg")

# Visit Leonida poster grid, in poster pixels, and poster px <-> metres.
P_S, P_DX, P_DY = 0.183, -186, -182
P_COLS = [105, 380, 672, 964, 1256, 1548, 1840, 2132, 2424, 2716]
P_ROWS = [105, 312, 604, 896, 1188, 1481, 1773, 2065, 2357, 2649, 2941, 3233, 3526, 3735]


def poster_to_ig(px, py):
    return (px - P_DX) / P_S - 12288, 12288 - (py - P_DY) / P_S


GRID_X = [poster_to_ig(c, 0)[0] for c in P_COLS]
GRID_Y = [poster_to_ig(0, r)[1] for r in P_ROWS]


def grid_ref(x, y):
    col = next((i + 1 for i in range(9) if GRID_X[i] <= x < GRID_X[i + 1]), None)
    row = next(("ABCDEFGHIJKLM"[i] for i in range(13) if GRID_Y[i] >= y > GRID_Y[i + 1]), None)
    return f"{row}{col}" if row and col else None


# Level 3 tiles: 4 m/px, level pixel 0 = -16384 m; the stitched image starts at tile 4.
M_PER_PX, T0 = 4, 4
SCALE = 0.75  # output downscale


def stitch():
    names = os.listdir(TILES)
    ys = [int(n.split(",")[1]) for n in names]
    xs = [int(n.split(",")[2].split(".")[0]) for n in names]
    im = Image.new("RGB", ((max(xs) - T0 + 1) * 256, (max(ys) - T0 + 1) * 256), (47, 144, 176))
    for n, x, y in zip(names, xs, ys):
        im.paste(Image.open(os.path.join(TILES, n)), ((x - T0) * 256, (y - T0) * 256))
    return im


def ig_to_stitched(x, y):
    return (x + 16384) / M_PER_PX - T0 * 256, (16384 - y) / M_PER_PX - T0 * 256


COLORS = {"conf": (46, 160, 67), "doc": (230, 160, 0), "single": (214, 69, 65)}
LABELS = {"conf": "Confirmed in gameplay (3+ guides)",
          "doc": "Credibly documented (2 sources)",
          "single": "Single source"}


def font(size, bold=True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)


def main():
    data = json.load(open(os.path.join(ROOT, "data/locations.json")))["locations"]
    base = stitch()
    x0, y0 = ig_to_stitched(GRID_X[0], GRID_Y[0])
    x1, y1 = ig_to_stitched(GRID_X[-1], GRID_Y[-1])
    base = base.crop((round(x0), round(y0), round(x1), round(y1)))
    base = base.resize((round(base.width * SCALE), round(base.height * SCALE)), Image.LANCZOS)
    W, H = base.size
    PANEL = 860
    img = Image.new("RGB", (W + PANEL, H), (16, 24, 32))
    img.paste(base, (0, 0))
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)

    def px(x, y):
        sx, sy = ig_to_stitched(x, y)
        return (sx - x0) * SCALE, (sy - y0) * SCALE

    # grid
    f_grid = font(30)
    for gx in GRID_X:
        X, _ = px(gx, 0)
        d.line([(X, 0), (X, H)], fill=(255, 255, 255, 90), width=2)
    for gy in GRID_Y:
        _, Y = px(0, gy)
        d.line([(0, Y), (W, Y)], fill=(255, 255, 255, 90), width=2)
    for i in range(9):
        cx = (px(GRID_X[i], 0)[0] + px(GRID_X[i + 1], 0)[0]) / 2
        for Y in (8, H - 42):
            d.text((cx, Y), str(i + 1), font=f_grid, fill=(255, 255, 255, 230), anchor="ma")
    for i in range(13):
        cy = (px(0, GRID_Y[i])[1] + px(0, GRID_Y[i + 1])[1]) / 2
        for X in (14, W - 14):
            d.text((X, cy), "ABCDEFGHIJKLM"[i], font=f_grid, fill=(255, 255, 255, 230),
                   anchor="lm" if X < W / 2 else "rm")

    # markers: greedy placement with leader lines so bubbles don't overlap
    R = 19
    f_num = font(20)
    placed = []
    shown = [m for m in data if m["x"] is not None and not m.get("same_as")]
    for m in shown:
        tx, ty = px(m["x"], m["y"])
        if m["precision"] in ("approx", "district"):
            r = 350 / M_PER_PX * SCALE  # ~350 m uncertainty halo
            d.ellipse((tx - r, ty - r, tx + r, ty + r), fill=COLORS[m["v"]] + (45,),
                      outline=COLORS[m["v"]] + (150,), width=2)
        best = None
        for k in range(0, 200):
            ang = k * 2.4
            dist = 0 if k == 0 else 2.2 * R + 9 * math.sqrt(k)
            bx, by = tx + dist * math.cos(ang), ty + dist * math.sin(ang)
            if all((bx - qx) ** 2 + (by - qy) ** 2 > (2 * R + 4) ** 2 for qx, qy in placed):
                best = (bx, by)
                break
        bx, by = best
        placed.append((bx, by))
        m["_tip"], m["_bubble"] = (tx, ty), (bx, by)
    for m in shown:
        (tx, ty), (bx, by) = m["_tip"], m["_bubble"]
        if (bx, by) != (tx, ty):
            d.line([(tx, ty), (bx, by)], fill=(255, 255, 255, 230), width=3)
            d.ellipse((tx - 5, ty - 5, tx + 5, ty + 5), fill=(255, 255, 255, 255))
    for m in shown:
        bx, by = m["_bubble"]
        label = "1-2" if m["n"] == 1 else str(m["n"])
        rr = R + (6 if len(label) > 2 else 0)
        d.ellipse((bx - rr, by - rr, bx + rr, by + rr), fill=COLORS[m["v"]] + (255,),
                  outline=(0, 0, 0, 255), width=3)
        d.text((bx, by), label, font=f_num, fill=(255, 255, 255, 255), anchor="mm",
               stroke_width=2, stroke_fill=(0, 0, 0, 255))
    img = Image.alpha_composite(img.convert("RGBA"), over)

    # legend panel
    d = ImageDraw.Draw(img)
    X = W + 30
    d.text((X, 30), "GTA VI: code-locked locations", font=font(34), fill="white")
    d.text((X, 76), "Research date 23 Nov 2026. # matches README.md.", font=font(20, False),
           fill=(190, 200, 210))
    Y = 120
    for k in ("conf", "doc", "single"):
        d.ellipse((X, Y, X + 26, Y + 26), fill=COLORS[k], outline="black", width=2)
        d.text((X + 38, Y + 13), LABELS[k], font=font(21, False), fill="white", anchor="lm")
        Y += 36
    d.ellipse((X, Y, X + 26, Y + 26), fill=(120, 120, 120), outline=(200, 200, 200), width=2)
    d.text((X + 38, Y + 13), "Halo = approximate (district / description)", font=font(21, False),
           fill="white", anchor="lm")
    Y += 52
    f_row, f_row_b = font(20, False), font(20)
    for m in data:
        g = grid_ref(m["x"], m["y"]) if m["x"] is not None else None
        pos = g if g else "-"
        d.ellipse((X, Y + 2, X + 18, Y + 20), fill=COLORS[m["v"]])
        d.text((X + 28, Y), f"{m['n']:>2}", font=f_row_b, fill="white")
        d.text((X + 66, Y), pos, font=f_row_b, fill=(255, 220, 120))
        name = m["name"] if len(m["name"]) <= 44 else m["name"][:43] + "…"
        d.text((X + 120, Y), name, font=f_row, fill="white")
        Y += 29
    Y += 14
    for line in ["Unplaced (-): no source gives a usable location.",
                 "Grid = the 'Visit Leonida' poster map grid.",
                 "Base map: GTA VI Map Tiles (CC BY 4.0) - map.gtadb.org,",
                 "cropped, scaled, with grid and markers added.",
                 "Landmark positions: GTA VI Landmarks Data (CC BY 4.0)",
                 "- map.gtadb.org."]:
        d.text((X, Y), line, font=font(18, False), fill=(190, 200, 210))
        Y += 25
    img.convert("RGB").save(OUT, quality=85, optimize=True)
    print(OUT, img.size, os.path.getsize(OUT))
    return {m["n"]: grid_ref(m["x"], m["y"]) if m["x"] is not None else None for m in data}


if __name__ == "__main__":
    print(json.dumps(main()))
