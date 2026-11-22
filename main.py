#!/usr/bin/env python3
"""The picture that tastes of one ingredient.

One strawberry. Nothing else. A single ripe strawberry, drawn procedurally
with the Python standard library only: warm cream background, one big glossy
berry with seeds, calyx and stem, a few water droplets, soft shadow.

Deterministic: no network, no clock, no unseeded randomness. Writes a
1024x1024 PNG to /output/entry.png (or ./entry.png when /output is absent).
"""
import math
import os
import struct
import zlib

W = H = 1024
buf = bytearray(W * H * 3)


def set_px(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        buf[i] = r
        buf[i + 1] = g
        buf[i + 2] = b


def blend_px(x, y, r, g, b, a):
    if 0 <= x < W and 0 <= y < H and a > 0.0:
        if a > 1.0:
            a = 1.0
        i = (y * W + x) * 3
        buf[i] = int(buf[i] + (r - buf[i]) * a)
        buf[i + 1] = int(buf[i + 1] + (g - buf[i + 1]) * a)
        buf[i + 2] = int(buf[i + 2] + (b - buf[i + 2]) * a)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


# ---------------------------------------------------------------- background
def paint_background():
    cx, cy, r2 = 512.0, 470.0, 780.0 * 780.0
    for y in range(H):
        dy = y - cy
        base = y * W * 3
        for x in range(W):
            dx = x - cx
            s = (dx * dx + dy * dy) / r2
            if s > 1.0:
                s = 1.0
            s = s * (2.0 - s)  # smooth falloff
            i = base + x * 3
            buf[i] = int(255 + (236 - 255) * s)
            buf[i + 1] = int(251 + (212 - 251) * s)
            buf[i + 2] = int(242 + (176 - 242) * s)


def soft_ellipse(cx, cy, rx, ry, r, g, b, amax):
    y0 = max(0, int(cy - ry))
    y1 = min(H - 1, int(cy + ry))
    for y in range(y0, y1 + 1):
        ny = (y - cy) / ry
        span = rx * math.sqrt(max(0.0, 1.0 - ny * ny))
        x0 = max(0, int(cx - span))
        x1 = min(W - 1, int(cx + span))
        for x in range(x0, x1 + 1):
            nx = (x - cx) / rx
            d = nx * nx + ny * ny
            if d >= 1.0:
                continue
            a = amax * (1.0 - d) * (1.0 - d)
            blend_px(x, y, r, g, b, a)


def fill_ellipse(cx, cy, rx, ry, r, g, b, a=1.0, shear=0.0):
    y0 = max(0, int(cy - ry))
    y1 = min(H - 1, int(cy + ry))
    for y in range(y0, y1 + 1):
        ny = (y - cy) / ry
        span = rx * math.sqrt(max(0.0, 1.0 - ny * ny))
        shift = (y - cy) * shear
        x0 = max(0, int(cx + shift - span))
        x1 = min(W - 1, int(cx + shift + span))
        for x in range(x0, x1 + 1):
            if a >= 1.0:
                set_px(x, y, r, g, b)
            else:
                blend_px(x, y, r, g, b, a)


def fill_poly(pts, r, g, b):
    ys = [p[1] for p in pts]
    y0 = max(0, int(min(ys)))
    y1 = min(H - 1, int(max(ys)))
    n = len(pts)
    for y in range(y0, y1 + 1):
        xs = []
        for i in range(n):
            x1, y1p = pts[i]
            x2, y2p = pts[(i + 1) % n]
            if (y1p <= y < y2p) or (y2p <= y < y1p):
                xs.append(x1 + (y - y1p) * (x2 - x1) / (y2p - y1p))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            x0 = max(0, int(xs[k]))
            x1 = min(W - 1, int(xs[k + 1]))
            for x in range(x0, x1 + 1):
                set_px(x, y, r, g, b)


def line(x0, y0, x1, y1, r, g, b, width=2):
    steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for s in range(steps + 1):
        t = s / steps
        cx = x0 + (x1 - x0) * t
        cy = y0 + (y1 - y0) * t
        fill_ellipse(cx, cy, width, width, r, g, b)


# ------------------------------------------------------------------- strawberry
PROFILE = [(0.00, 0.55), (0.08, 0.88), (0.22, 1.00), (0.45, 0.92),
           (0.65, 0.74), (0.85, 0.45), (0.97, 0.16), (1.00, 0.00)]


def profile(t):
    for i in range(len(PROFILE) - 1):
        t0, w0 = PROFILE[i]
        t1, w1 = PROFILE[i + 1]
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            f = (1.0 - math.cos(f * math.pi)) / 2.0
            return w0 + (w1 - w0) * f
    return 0.0


Y_TOP, Y_BOT, WMAX, CX = 250, 890, 290, 512


def paint_body():
    # top edge dips at the centre where the calyx sits
    top_edge = []
    for x in range(CX - WMAX, CX + WMAX + 1):
        dx = (x - CX) / 120.0
        top_edge.append(Y_TOP + 48.0 * math.exp(-dx * dx))
    for y in range(Y_TOP, Y_BOT + 1):
        t = (y - Y_TOP) / (Y_BOT - Y_TOP)
        w = WMAX * profile(t)
        x0 = int(CX - w)
        x1 = int(CX + w)
        for x in range(x0, x1 + 1):
            dx = x - CX
            if dx * dx > w * w:
                continue
            if y < top_edge[x - (CX - WMAX)]:
                continue
            # gloss centre upper-left; deep red toward rim and base
            u = ((x - 400.0) / 360.0) ** 2 + ((y - 420.0) / 400.0) ** 2
            if u > 1.0:
                u = 1.0
            uu = u * 1.5
            if uu > 1.0:
                uu = 1.0
            r = 255.0 + (231.0 - 255.0) * uu
            g = 112.0 + (32.0 - 112.0) * uu
            b = 90.0 + (40.0 - 90.0) * uu
            deep = 0.35 * t + 0.45 * max(0.0, u - 0.55) / 0.45
            if deep > 0.75:
                deep = 0.75
            r += (150.0 - r) * deep
            g += (12.0 - g) * deep
            b += (28.0 - b) * deep
            rim = (abs(dx) / w - 0.82) / 0.18 if w > 0 else 0.0
            if rim > 0.0:
                if rim > 1.0:
                    rim = 1.0
                f = 1.0 - 0.25 * rim
                r *= f
                g *= f
                b *= f
            # faint organic mottling, deterministic
            n = (x * 31 + y * 17) % 13 - 6
            i = (y * W + x) * 3
            buf[i] = clamp(int(r) + n, 0, 255)
            buf[i + 1] = clamp(int(g) + n // 2, 0, 255)
            buf[i + 2] = clamp(int(b) + n // 2, 0, 255)


def paint_seeds():
    rows = [0.16 + 0.08 * k for k in range(10)]
    for ri, t in enumerate(rows):
        y = Y_TOP + t * (Y_BOT - Y_TOP)
        w = WMAX * profile(t)
        spacing = 54.0
        offset = 27.0 if ri % 2 else 0.0
        x = CX - w * 0.85 + offset
        while x < CX + w * 0.85:
            dx = x - CX
            shear = clamp(dx / 600.0, -0.35, 0.35)
            # dimple, then the pale seed, then a bright speck
            fill_ellipse(x, y + 3, 8.0, 12.0, 120, 10, 22, a=0.45, shear=shear)
            fill_ellipse(x, y, 5.5, 9.0, 255, 224, 138, shear=shear)
            fill_ellipse(x - 1.5, y - 3.5, 1.8, 2.6, 255, 248, 210, shear=shear)
            x += spacing


def paint_droplets():
    for cx, cy, r in [(430, 480, 14), (600, 520, 11), (480, 650, 16),
                      (620, 700, 9), (400, 760, 12), (560, 420, 8),
                      (655, 600, 10), (520, 800, 9)]:
        y0 = max(0, int(cy - r))
        y1 = min(H - 1, int(cy + r))
        for y in range(y0, y1 + 1):
            for x in range(max(0, int(cx - r)), min(W - 1, int(cx + r)) + 1):
                d = ((x - cx) / r) ** 2 + ((y - cy) / r) ** 2
                if d >= 1.0:
                    continue
                a = 0.42 * (1.0 - d) * (1.0 - d)
                blend_px(x, y, 235, 245, 255, a)
        fill_ellipse(cx - r * 0.35, cy - r * 0.4, r * 0.28, r * 0.2,
                     255, 255, 255, a=0.85)


def paint_calyx():
    # stem first (behind the leaves), then leaves, then the centre cap
    fill_poly([(505, 298), (519, 298), (521, 196), (511, 192)], 104, 110, 58)
    line(511, 290, 517, 200, 140, 148, 84, width=2)
    angles = [-72, -45, -20, 8, 35, 62]
    lengths = [150, 168, 175, 172, 165, 148]
    greens = [(74, 122, 52), (92, 146, 62), (62, 108, 44),
              (98, 152, 66), (70, 118, 50), (88, 140, 58)]
    bx, by = 512.0, 292.0
    for ang, L, (gr, gg, gb) in zip(angles, lengths, greens):
        th = math.radians(ang)
        dx, dy = math.sin(th), -math.cos(th)  # up = -y
        px, py = math.cos(th), math.sin(th)   # perpendicular
        bw = 20.0
        tip = (bx + dx * L, by + dy * L)
        ml = (bx + dx * L * 0.55 - px * bw * 1.5,
              by + dy * L * 0.55 - py * bw * 1.5)
        mr = (bx + dx * L * 0.55 + px * bw * 1.5,
              by + dy * L * 0.55 + py * bw * 1.5)
        bl = (bx - px * bw, by - py * bw)
        br = (bx + px * bw, by + py * bw)
        fill_poly([bl, ml, tip, mr, br], gr, gg, gb)
        line(bx, by, tip[0], tip[1], 44, 82, 32, width=2)
    fill_ellipse(512, 292, 30, 22, 58, 104, 42)


# ------------------------------------------------------------------------ png
def write_png(path):
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        raw += buf[y * W * 3:(y + 1) * W * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data +
                struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    paint_background()
    soft_ellipse(512, 905, 310, 48, 96, 52, 32, 0.28)  # soft shadow
    paint_body()
    paint_seeds()
    soft_ellipse(415, 430, 150, 110, 255, 255, 255, 0.13)  # gloss
    soft_ellipse(455, 395, 62, 42, 255, 255, 255, 0.10)
    paint_droplets()
    paint_calyx()
    if os.path.isdir("/output"):
        path = "/output/entry.png"
    else:
        path = "entry.png"
    size = write_png(path)
    print("wrote %s (%d bytes)" % (path, size))


if __name__ == "__main__":
    main()
