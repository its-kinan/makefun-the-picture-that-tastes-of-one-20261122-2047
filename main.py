#!/usr/bin/env python3
"""One Strawberry - a single ripe strawberry, drawn procedurally in pure Python.

Standard library only. Fully deterministic: no clock, no randomness, no
network. Writes a 1024x1024 PNG (own encoder) to /output/entry.png when
/output exists, otherwise ./entry.png in the current directory.
"""

import math
import os
import struct
import zlib

W = 1024
H = 1024

buf = bytearray(W * H * 3)
mask = bytearray(W * H)  # 1 where the berry body is


def set_px(x, y, r, g, b):
    i = (y * W + x) * 3
    buf[i] = r
    buf[i + 1] = g
    buf[i + 2] = b


def blend_px(x, y, r, g, b, a):
    i = (y * W + x) * 3
    ia = 1.0 - a
    buf[i] = int(buf[i] * ia + r * a + 0.5)
    buf[i + 1] = int(buf[i + 1] * ia + g * a + 0.5)
    buf[i + 2] = int(buf[i + 2] * ia + b * a + 0.5)


def clamp255(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


# ---------------------------------------------------------------- background
def draw_background():
    for y in range(H):
        dy = y - 470
        row = y * W
        for x in range(W):
            dx = x - 512
            d = math.sqrt(dx * dx + dy * dy) / 780.0
            if d > 1.0:
                d = 1.0
            s = d * d * (3.0 - 2.0 * d)  # smoothstep falloff
            i = (row + x) * 3
            buf[i] = int(255 + (236 - 255) * s + 0.5)
            buf[i + 1] = int(251 + (212 - 251) * s + 0.5)
            buf[i + 2] = int(242 + (176 - 242) * s + 0.5)


# ---------------------------------------------------------------- soft shadow
def draw_shadow():
    for y in range(905 - 48, 905 + 49):
        dy = (y - 905) / 48.0
        for x in range(512 - 310, 512 + 311):
            dx = (x - 512) / 310.0
            q = dx * dx + dy * dy
            if q < 1.0:
                blend_px(x, y, 96, 52, 32, 0.28 * (1.0 - q))


# ---------------------------------------------------------------- berry shape
PROFILE = [
    (0.00, 0.55), (0.08, 0.88), (0.22, 1.00), (0.45, 0.92),
    (0.65, 0.74), (0.85, 0.45), (0.97, 0.16), (1.00, 0.00),
]


def half_width(t):
    for i in range(len(PROFILE) - 1):
        t0, w0 = PROFILE[i]
        t1, w1 = PROFILE[i + 1]
        if t0 <= t <= t1:
            mu = (t - t0) / (t1 - t0)
            mu = (1.0 - math.cos(math.pi * mu)) / 2.0  # cosine interpolation
            return (w0 + (w1 - w0) * mu) * 290.0
    return 0.0


# Top edge dips at the centre where the calyx sits (depends on x only).
TOP_Y = {}
for _x in range(202, 823):
    TOP_Y[_x] = 250.0 + 48.0 * math.exp(-(((_x - 512) / 120.0) ** 2))


def draw_body():
    for y in range(250, 891):
        t = (y - 250) / 640.0
        hw = half_width(t)
        if hw <= 0.0:
            continue
        x0 = int(math.ceil(512 - hw))
        x1 = int(math.floor(512 + hw))
        for x in range(x0, x1 + 1):
            if y < TOP_Y[x]:
                continue
            # --- base colour: highlight -> mid red -> deep red
            u = ((x - 400) / 360.0) ** 2 + ((y - 420) / 400.0) ** 2
            if u > 1.0:
                u = 1.0
            w = u * 1.5
            if w > 1.0:
                w = 1.0
            r = 255.0 + (231.0 - 255.0) * w
            g = 112.0 + (32.0 - 112.0) * w
            b = 90.0 + (40.0 - 90.0) * w
            deep = 0.45 * t + 0.6 * max(0.0, u - 0.55) / 0.45
            if deep > 0.75:
                deep = 0.75
            r += (150.0 - r) * deep
            g += (12.0 - g) * deep
            b += (28.0 - b) * deep
            # --- darken the rim
            rr = abs(x - 512) / hw
            if rr > 0.82:
                s = 1.0 - 0.25 * (rr - 0.82) / 0.18
                r *= s
                g *= s
                b *= s
            # --- faint deterministic mottling
            m = (x * 31 + y * 17) % 13 - 6
            r += m
            g += m // 2
            b += m // 2
            i = (y * W + x) * 3
            buf[i] = clamp255(r)
            buf[i + 1] = clamp255(g)
            buf[i + 2] = clamp255(b)
            mask[y * W + x] = 1


# ---------------------------------------------------------------- helpers
def ellipse(cx, cy, rx, ry, r, g, b, a=1.0, shear=0.0, only_mask=False):
    x0 = int(math.floor(cx - rx)) - 1
    x1 = int(math.ceil(cx + rx)) + 1
    y0 = int(math.floor(cy - ry)) - 1
    y1 = int(math.ceil(cy + ry)) + 1
    for y in range(max(0, y0), min(H, y1 + 1)):
        for x in range(max(0, x0), min(W, x1 + 1)):
            if only_mask and not mask[y * W + x]:
                continue
            dx = x - cx
            dy = y - cy - shear * dx
            q = (dx / rx) ** 2 + (dy / ry) ** 2
            if q <= 1.0:
                if a >= 1.0:
                    set_px(x, y, r, g, b)
                else:
                    blend_px(x, y, r, g, b, a)


def radial_glow(cx, cy, rx, ry, r, g, b, a_max, only_mask=True):
    x0 = int(math.floor(cx - rx)) - 1
    x1 = int(math.ceil(cx + rx)) + 1
    y0 = int(math.floor(cy - ry)) - 1
    y1 = int(math.ceil(cy + ry)) + 1
    for y in range(max(0, y0), min(H, y1 + 1)):
        for x in range(max(0, x0), min(W, x1 + 1)):
            if only_mask and not mask[y * W + x]:
                continue
            dx = (x - cx) / rx
            dy = (y - cy) / ry
            q = dx * dx + dy * dy
            if q < 1.0:
                blend_px(x, y, r, g, b, a_max * (1.0 - math.sqrt(q)))


def fill_poly(pts, r, g, b):
    ys = [p[1] for p in pts]
    y0 = int(min(ys))
    y1 = int(max(ys))
    n = len(pts)
    for y in range(max(0, y0), min(H, y1 + 1)):
        xs = []
        for i in range(n):
            x1, y1p = pts[i]
            x2, y2p = pts[(i + 1) % n]
            if (y1p <= y < y2p) or (y2p <= y < y1p):
                xs.append(x1 + (y - y1p) * (x2 - x1) / (y2p - y1p))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            for x in range(int(math.ceil(xs[k])), int(math.floor(xs[k + 1])) + 1):
                if 0 <= x < W:
                    set_px(x, y, r, g, b)


def thick_line(x0, y0, x1, y1, w, r, g, b):
    steps = int(max(abs(x1 - x0), abs(y1 - y0))) * 2 + 1
    rr = w / 2.0
    for s in range(steps + 1):
        f = s / steps
        cx = x0 + (x1 - x0) * f
        cy = y0 + (y1 - y0) * f
        for yy in range(int(cy - rr) - 1, int(cy + rr) + 2):
            for xx in range(int(cx - rr) - 1, int(cx + rr) + 2):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= rr * rr:
                    if 0 <= xx < W and 0 <= yy < H:
                        set_px(xx, yy, r, g, b)


# ---------------------------------------------------------------- seeds
def draw_seeds():
    for row in range(10):
        t = 0.16 + row * 0.08
        y = 250 + t * 640
        hw = half_width(t)
        limit = 0.85 * hw
        off = 27.0 if row % 2 else 0.0
        base = 512.0 + off
        n0 = math.ceil((512.0 - limit - base) / 54.0)
        x = base + n0 * 54.0
        while x <= 512.0 + limit:
            shear = 0.35 * (x - 512.0) / 290.0
            # dark-red dimple, shifted down 3px
            ellipse(x, y + 3, 8, 12, 120, 10, 20, a=0.45, shear=shear,
                    only_mask=True)
            # pale gold seed
            ellipse(x, y, 5.5, 9, 255, 224, 138, shear=shear, only_mask=True)
            # tiny bright speck near its top-left
            ellipse(x - 2, y - 4, 1.8, 1.2, 255, 250, 220, a=0.95,
                    only_mask=True)
            x += 54.0


# ---------------------------------------------------------------- gloss + dew
def draw_gloss():
    radial_glow(415, 430, 150, 110, 255, 255, 255, 0.13)
    radial_glow(455, 395, 62, 42, 255, 255, 255, 0.10)


DROPLETS = [
    (430, 480, 14), (600, 520, 11), (480, 650, 16), (620, 700, 9),
    (400, 760, 12), (560, 420, 8), (655, 600, 10), (520, 800, 9),
]


def draw_droplets():
    for cx, cy, r in DROPLETS:
        radial_glow(cx, cy, r, r, 235, 245, 255, 0.6)
        ellipse(cx - r * 0.35, cy - r * 0.4, max(1.5, r * 0.25),
                max(1.5, r * 0.25), 255, 255, 255, a=0.9, only_mask=True)


# ---------------------------------------------------------------- calyx + stem
LEAVES = [  # (angle deg from vertical, length, colour)
    (-72, 150, (74, 122, 52)),
    (-45, 168, (92, 146, 62)),
    (-20, 175, (62, 108, 44)),
    (8, 172, (98, 152, 66)),
    (35, 165, (70, 118, 50)),
    (62, 148, (88, 140, 58)),
]


def draw_calyx_stem():
    # stem: tapered polygon up from the berry
    fill_poly([(505, 298), (519, 298), (521, 196), (511, 192)], 104, 110, 58)
    thick_line(512, 292, 516, 194, 3, 140, 148, 84)
    # six pointed leaves fanning from (512, 292)
    bx, by = 512.0, 292.0
    for ang, length, col in LEAVES:
        a = math.radians(ang)
        dx, dy = math.sin(a), -math.cos(a)      # leaf direction
        px, py = math.cos(a), math.sin(a)       # perpendicular
        tip = (bx + dx * length, by + dy * length)
        mid = (bx + dx * length * 0.45, by + dy * length * 0.45)
        bl = (bx - px * 20, by - py * 20)
        ml = (mid[0] - px * 34, mid[1] - py * 34)
        mr = (mid[0] + px * 34, mid[1] + py * 34)
        br = (bx + px * 20, by + py * 20)
        fill_poly([bl, ml, tip, mr, br], col[0], col[1], col[2])
        dark = (int(col[0] * 0.55), int(col[1] * 0.55), int(col[2] * 0.55))
        thick_line(bx, by, tip[0], tip[1], 2, dark[0], dark[1], dark[2])
    # centre cap
    ellipse(512, 292, 30, 22, 58, 104, 42)


# ---------------------------------------------------------------- PNG encoder
def _chunk(typ, data):
    out = struct.pack(">I", len(data)) + typ + data
    out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return out


def write_png(path):
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        raw += buf[y * W * 3:(y + 1) * W * 3]
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", ihdr)
           + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + _chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    draw_background()
    draw_shadow()
    draw_body()
    draw_seeds()
    draw_gloss()
    draw_droplets()
    draw_calyx_stem()
    out = "/output/entry.png" if os.path.isdir("/output") else "./entry.png"
    n = write_png(out)
    print(f"wrote {out} ({n} bytes)")


if __name__ == "__main__":
    main()
