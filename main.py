"""One Strawberry -- a single ripe strawberry, procedurally drawn.

Pure Python, standard library only: no PIL, no network, no clock,
no unseeded randomness. Fully deterministic -- running this script
twice produces a byte-identical PNG.

Canvas: 1024x1024 RGB. One ingredient, one look, one taste.
"""

import math
import os
import struct
import zlib

W, H = 1024, 1024


def clamp(v, lo=0, hi=255):
    return lo if v < lo else hi if v > hi else v


def clampf(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def smoothstep(a, b, x):
    """Smooth 0->1 ramp between a and b."""
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    t = (x - a) / (b - a)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    t = clampf(t)
    return (
        int(lerp(c1[0], c2[0], t)),
        int(lerp(c1[1], c2[1], t)),
        int(lerp(c1[2], c2[2], t)),
    )


def blend(dst, src, alpha):
    """Alpha-blend src over dst; alpha in [0, 1]."""
    a = clampf(alpha)
    return (
        int(src[0] * a + dst[0] * (1.0 - a)),
        int(src[1] * a + dst[1] * (1.0 - a)),
        int(src[2] * a + dst[2] * (1.0 - a)),
    )


class Canvas:
    """Simple RGB pixel buffer with primitive ellipse/point drawing."""

    def __init__(self, w, h, fill):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)
        r, g, b = fill
        for i in range(0, len(self.px), 3):
            self.px[i] = r
            self.px[i + 1] = g
            self.px[i + 2] = b

    def set(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i] = color[0]
            self.px[i + 1] = color[1]
            self.px[i + 2] = color[2]

    def get(self, x, y):
        i = (y * self.w + x) * 3
        return (self.px[i], self.px[i + 1], self.px[i + 2])

    def blend(self, x, y, color, alpha):
        if 0 <= x < self.w and 0 <= y < self.h and alpha > 0.0:
            self.set(x, y, blend(self.get(x, y), color, alpha))

    def fill_ellipse(self, cx, cy, rx, ry, color, alpha=1.0, shear=0.0):
        """Fill an ellipse (optionally sheared in x by y) with flat alpha."""
        x0 = max(0, int(cx - rx - abs(shear) * ry - 2))
        x1 = min(self.w - 1, int(cx + rx + abs(shear) * ry + 2))
        y0 = max(0, int(cy - ry - 2))
        y1 = min(self.h - 1, int(cy + ry + 2))
        for y in range(y0, y1 + 1):
            dy = (y - cy) / ry
            if dy * dy > 1.0:
                continue
            half = rx * math.sqrt(1.0 - dy * dy)
            shift = shear * (y - cy)
            xa = int(cx + shift - half)
            xb = int(cx + shift + half)
            if xa < x0:
                xa = x0
            if xb > x1:
                xb = x1
            for x in range(xa, xb + 1):
                self.blend(x, y, color, alpha)

    def radial_ellipse(self, cx, cy, rx, ry, color, alpha, shear=0.0):
        """Ellipse filled with a radial alpha falloff to 0 at the rim."""
        x0 = max(0, int(cx - rx - abs(shear) * ry - 2))
        x1 = min(self.w - 1, int(cx + rx + abs(shear) * ry + 2))
        y0 = max(0, int(cy - ry - 2))
        y1 = min(self.h - 1, int(cy + ry + 2))
        for y in range(y0, y1 + 1):
            dy = (y - cy) / ry
            for x in range(x0, x1 + 1):
                dx = (x - cx - shear * (y - cy)) / rx
                d2 = dx * dx + dy * dy
                if d2 > 1.0:
                    continue
                a = alpha * (1.0 - math.sqrt(d2))
                self.blend(x, y, color, a)

    def draw_line(self, x0, y0, x1, y1, color, alpha=1.0, width=1):
        """Simple DDA line, width in pixels (square brush)."""
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        half = width // 2
        for i in range(steps + 1):
            t = i / steps if steps else 0.0
            x = int(round(x0 + (x1 - x0) * t))
            y = int(round(y0 + (y1 - y0) * t))
            for dy in range(-half, half + 1):
                for dx in range(-half, half + 1):
                    self.blend(x + dx, y + dy, color, alpha)

    def fill_polygon(self, points, color, alpha=1.0):
        """Scanline polygon fill (even-odd via scanline intersections)."""
        ys = [p[1] for p in points]
        y0 = max(0, int(min(ys)))
        y1 = min(self.h - 1, int(max(ys)) + 1)
        n = len(points)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x_a, y_a = points[i]
                x_b, y_b = points[(i + 1) % n]
                if (y_a <= y < y_b) or (y_b <= y < y_a):
                    t = (y - y_a) / (y_b - y_a)
                    xs.append(x_a + t * (x_b - x_a))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                xa = max(0, int(math.ceil(xs[k])))
                xb = min(self.w - 1, int(math.floor(xs[k + 1])))
                for x in range(xa, xb + 1):
                    self.blend(x, y, color, alpha)


# ---------------------------------------------------------------- PNG

def _chunk(kind, data):
    out = struct.pack(">I", len(data))
    out += kind
    out += data
    out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return out


def write_png(canvas, path):
    raw = bytearray()
    for y in range(canvas.h):
        raw.append(0)  # filter: none
        raw.extend(canvas.px[y * canvas.w * 3:(y + 1) * canvas.w * 3])
    ihdr = struct.pack(">IIBBBBB", canvas.w, canvas.h, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n"
    data += _chunk(b"IHDR", ihdr)
    data += _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    data += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


# ------------------------------------------------------- background

def draw_background(cv):
    cx, cy, r = 512.0, 470.0, 780.0
    inner = (255, 251, 242)
    outer = (236, 212, 176)
    for y in range(H):
        for x in range(W):
            d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2) / r
            d = clampf(d)
            t = d * d * (3.0 - 2.0 * d)  # smooth falloff
            cv.set(x, y, lerp_color(inner, outer, t))


def draw_shadow(cv):
    # Soft ellipse under the berry, alpha peaking at 0.28 in the centre.
    cv.radial_ellipse(512, 905, 310, 48, (96, 52, 32), 0.28)


# ------------------------------------------------------- berry shape

TOP_Y = 250.0
TIP_Y = 890.0
CENTER_X = 512.0
MAX_HW = 290.0


def half_width(t):
    """Half-width fraction at depth t in [0, 1] along the berry."""
    ramp = smoothstep(0.0, 0.22, t)
    taper = (1.0 - t ** 2.8) ** 0.72 if t < 1.0 else 0.0
    return ramp * taper


def top_edge_y(x):
    """Top edge dips at the centre where the calyx sits."""
    return TOP_Y + 48.0 * math.exp(-((x - CENTER_X) / 120.0) ** 2)


def berry_colour(x, y, t, hw):
    """Red gradient: bright gloss near (400,420), deep red at depth/rim."""
    u = ((x - 400.0) / 360.0) ** 2 + ((y - 420.0) / 400.0) ** 2
    u = clampf(u)
    c = lerp_color((255, 112, 90), (231, 32, 40), clampf(u * 1.5))
    deep = clampf((t * 0.9 + max(0.0, u - 0.55) * 1.4) * 0.85, 0.0, 0.75)
    c = lerp_color(c, (150, 12, 28), deep)
    # Darken the rim.
    rim = abs(x - CENTER_X) / hw if hw > 0 else 0.0
    if rim > 0.82:
        scale = 1.0 - 0.25 * ((rim - 0.82) / 0.18)
        c = (int(c[0] * scale), int(c[1] * scale), int(c[2] * scale))
    # Faint deterministic mottling.
    m = (x * 31 + y * 17) % 13 - 6
    return (
        clamp(c[0] + m),
        clamp(c[1] + m // 2),
        clamp(c[2] + m // 2),
    )


def draw_berry(cv):
    for y in range(int(TOP_Y), int(TIP_Y) + 1):
        t = (y - TOP_Y) / (TIP_Y - TOP_Y)
        hw = MAX_HW * half_width(t)
        if hw <= 0.5:
            continue
        x0 = int(CENTER_X - hw)
        x1 = int(CENTER_X + hw)
        top = top_edge_y(CENTER_X)  # dip is per-x; checked below
        for x in range(x0, x1 + 1):
            if y < top_edge_y(x):
                continue
            cv.set(x, y, berry_colour(x, y, t, hw))


# ------------------------------------------------------- gloss

def draw_gloss(cv):
    cv.radial_ellipse(415, 430, 150, 110, (255, 255, 255), 0.13)
    cv.radial_ellipse(455, 395, 62, 42, (255, 255, 255), 0.10)


# ------------------------------------------------------- seeds

def draw_seeds(cv):
    t = 0.16
    row = 0
    while t <= 0.881:
        y = int(TOP_Y + t * (TIP_Y - TOP_Y))
        hw = MAX_HW * half_width(t)
        if hw > 20:
            offset = 27.0 if row % 2 else 0.0
            x = CENTER_X - 0.85 * hw + offset
            # Start a touch inside the left edge so seeds sit on the body.
            while x < CENTER_X + 0.85 * hw:
                if abs(x - CENTER_X) < 0.85 * hw:
                    shear = (x - CENTER_X) / hw * 0.18
                    # Translucent dark-red dimple, shifted down 3px.
                    cv.fill_ellipse(x, y + 3, 8, 12, (120, 10, 22),
                                    alpha=0.45, shear=shear)
                    # Pale gold seed.
                    cv.fill_ellipse(x, y, 5.5, 9, (255, 224, 138),
                                    shear=shear)
                    # Tiny bright speck near the top-left of the seed.
                    cv.fill_ellipse(x - 2, y - 4, 1.6, 2.2,
                                    (255, 246, 200), shear=shear)
                x += 54.0
        t += 0.08
        row += 1


# ------------------------------------------------------- droplets

DROPLETS = [
    (430, 480, 14), (600, 520, 11), (480, 650, 16), (620, 700, 9),
    (400, 760, 12), (560, 420, 8), (655, 600, 10), (520, 800, 9),
]


def draw_droplets(cv):
    for (x, y, r) in DROPLETS:
        cv.radial_ellipse(x, y, r, r, (235, 245, 255), 0.55)
        cv.fill_ellipse(x - r * 0.35, y - r * 0.35, r * 0.22, r * 0.22,
                        (255, 255, 255), alpha=0.9)


# ------------------------------------------------------- calyx & stem

LEAVES = [
    # (angle deg from vertical, length, colour)
    (-72, 150, (74, 122, 52)),
    (-45, 168, (92, 146, 62)),
    (-20, 175, (62, 108, 44)),
    (8, 172, (98, 152, 66)),
    (35, 165, (70, 118, 50)),
    (62, 148, (88, 140, 58)),
]


def _leaf_points(cx, cy, angle_deg, length):
    """Five-point tapered leaf: base-left, mid-left bulge, tip,
    mid-right bulge, base-right. Angle measured from vertical."""
    a = math.radians(angle_deg)
    dx, dy = math.sin(a), -math.cos(a)  # tip direction (up is -y)
    px, py = math.cos(a), math.sin(a)   # perpendicular
    bx, by = cx, cy
    tx, ty = cx + dx * length, cy + dy * length
    half = 20.0
    mid = 0.45
    mx, my = cx + dx * length * mid, cy + dy * length * mid
    bulge = 26.0
    return [
        (bx - px * half, by - py * half),
        (mx - px * bulge, my - py * bulge),
        (tx, ty),
        (mx + px * bulge, my + py * bulge),
        (bx + px * half, by + py * half),
    ]


def draw_calyx(cv):
    cx, cy = 512.0, 292.0
    for angle, length, colour in LEAVES:
        pts = _leaf_points(cx, cy, angle, length)
        cv.fill_polygon(pts, colour)
        # Darker centre vein from base to tip.
        a = math.radians(angle)
        tx, ty = cx + math.sin(a) * length * 0.92, cy - math.cos(a) * length * 0.92
        dark = (max(0, colour[0] - 28), max(0, colour[1] - 30),
                max(0, colour[2] - 24))
        cv.draw_line(int(cx), int(cy), int(tx), int(ty), dark, width=2)
    # Centre cap over the leaf bases.
    cv.fill_ellipse(512, 292, 30, 22, (58, 104, 42))
    # Stem, drawn last so it peeks above the leaves.
    cv.draw_line(512, 292, 528, 150, (104, 110, 58), width=7)
    cv.draw_line(515, 285, 528, 155, (140, 146, 88), width=2)


# ------------------------------------------------------- entry point

def main():
    cv = Canvas(W, H, (255, 251, 242))
    draw_background(cv)
    draw_shadow(cv)
    draw_berry(cv)
    draw_gloss(cv)
    draw_seeds(cv)
    draw_droplets(cv)
    draw_calyx(cv)
    out = "/output/entry.png" if os.path.isdir("/output") else "entry.png"
    n = write_png(cv, out)
    print(f"wrote {out} ({n} bytes)")


if __name__ == "__main__":
    main()
