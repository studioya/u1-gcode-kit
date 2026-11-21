"""Small 2D path helpers for calibration prints."""
from __future__ import annotations
import math


def rect_loop(x0, y0, x1, y1):
    """Closed rectangle, counter-clockwise, starting at (x0, y0)."""
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def inset_loops(x0, y0, x1, y1, n, w):
    """n concentric rectangle loops from the outside in; first loop's outer edge at the box."""
    loops = []
    for i in range(n):
        d = w / 2 + i * w
        loops.append(rect_loop(x0 + d, y0 + d, x1 - d, y1 - d))
    return loops


def zigzag_fill(x0, y0, x1, y1, spacing, horizontal=True):
    """Boustrophedon fill of a box (bead centres inside the box). Returns a list of strokes."""
    strokes = []
    if horizontal:
        n = max(1, int(math.floor((y1 - y0) / spacing)) + 1)
        for i in range(n):
            y = y0 + i * spacing
            if y > y1 + 1e-9:
                break
            a, b = (x0, x1) if i % 2 == 0 else (x1, x0)
            strokes.append([(a, y), (b, y)])
    else:
        n = max(1, int(math.floor((x1 - x0) / spacing)) + 1)
        for i in range(n):
            x = x0 + i * spacing
            if x > x1 + 1e-9:
                break
            a, b = (y0, y1) if i % 2 == 0 else (y1, y0)
            strokes.append([(x, a), (x, b)])
    return strokes


def circle(cx, cy, r, n=48, start_deg=0.0):
    return [(cx + r * math.cos(math.radians(start_deg + 360 * k / n)),
             cy + r * math.sin(math.radians(start_deg + 360 * k / n))) for k in range(n)]
