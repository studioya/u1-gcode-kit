"""P2 - Head alignment verniers + per-head first-layer pads (printer layer).

Verniers: head 1 prints a main comb (bars every 1.00 mm); head N prints a
vernier comb (bars every 0.95 mm) butting against it. Where a pair of bars lines
up, read its index i (counting from the long centre bar, + toward the right in
X verniers and toward the back in Y verniers):

    offset of head N relative to head 1 = 0.05 mm * i   (range +/- 0.5 mm)

Each vernier has small square dots beside it: number of dots = head number.
Main combs are 2 layers; vernier combs are 3 layers so they stand proud and
can be read by raking light even if colours are close.

First-layer pads: one 20 x 20 mm two-layer pad per head (target 0.40 mm thick).
Measure each with calipers at the centre and four corners.

Best read with high-contrast colours: head 1 = reference spool, heads 2-4 any
colour that stands out against it. All PLA, so bed and chamber suit everyone.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from u1kit import records, shapes  # noqa: E402
from u1kit.writer import Job  # noqa: E402

HEADS = {0: "white-pla", 1: "clear-pla", 2: "generic-pla", 3: "yellow-pla"}  # head 3: swap the ABS for any contrasting PLA
LW = 0.45
H = 0.2
PITCH_MAIN, PITCH_VERN = 1.00, 0.95
N = 10                      # bars i = -N..N
BAR = 6.0                   # bar length
PAD = 20.0
PAD_Y = 205.0
PAD_X = {0: 45.0, 1: 100.0, 2: 155.0, 3: 210.0}
# vernier centres per partner head: (X-vernier centre, Y-vernier centre)
VERN = {1: ((60.0, 150.0), (60.0, 95.0)),
        2: ((135.0, 150.0), (135.0, 95.0)),
        3: ((210.0, 150.0), (210.0, 95.0))}


def _ext(i):
    """Index marks: centre bar +3 mm, every 5th +1.5 mm."""
    return 3.0 if i == 0 else (1.5 if i % 5 == 0 else 0.0)


def main_comb_x(cx, cy):
    """Head-1 comb for an X vernier: vertical bars above the joint line y=cy."""
    out = []
    for i in range(-N, N + 1):
        x = cx + i * PITCH_MAIN
        out.append([(x, cy + 0.1), (x, cy + BAR + _ext(i))])
    return out


def vern_comb_x(cx, cy):
    out = []
    for i in range(-N, N + 1):
        x = cx + i * PITCH_VERN
        out.append([(x, cy - 0.1), (x, cy - BAR - _ext(i))])
    return out


def main_comb_y(cx, cy):
    """Head-1 comb for a Y vernier: horizontal bars right of the joint line x=cx."""
    out = []
    for i in range(-N, N + 1):
        y = cy + i * PITCH_MAIN
        out.append([(cx + 0.1, y), (cx + BAR + _ext(i), y)])
    return out


def vern_comb_y(cx, cy):
    out = []
    for i in range(-N, N + 1):
        y = cy + i * PITCH_VERN
        out.append([(cx - 0.1, y), (cx - BAR - _ext(i), y)])
    return out


def dots(x, y, n, step=4.0, size=2.4):
    """n little filled squares in a row starting at (x, y)."""
    out = []
    for k in range(n):
        x0 = x + k * step
        out.append(shapes.rect_loop(x0, y, x0 + size, y + size) + [(x0, y)])
        out.append([(x0 + size / 2, y + 0.45), (x0 + size / 2, y + size - 0.45)])
    return out


def pad(job, t, layer_idx, speed):
    x0, y0 = PAD_X[t], PAD_Y
    x1, y1 = x0 + PAD, y0 + PAD
    loop = shapes.inset_loops(x0, y0, x1, y1, 1, LW)[0]
    job.path(loop, LW, speed, closed=True)
    inner = LW * 1.5
    strokes = shapes.zigzag_fill(x0 + inner, y0 + inner, x1 - inner, y1 - inner, LW,
                                 horizontal=(layer_idx % 2 == 0))
    job.travel(*strokes[0][0])
    for s in strokes:
        if (job.x, job.y) != s[0]:
            job.line_to(*s[0], LW, speed)   # connect zig-zag ends without lifting
        job.line_to(*s[1], LW, speed)


def bars(job, strokes, speed):
    for s in strokes:
        job.path(s, LW, speed)


def print_head(job, t, layer_idx):
    speed = 25.0 if layer_idx == 0 else 35.0
    job.tool(t)
    if layer_idx < 2:
        pad(job, t, layer_idx, speed)       # the pad also re-primes the head after a swap
    else:
        # layer 3: no pad, so re-prime with one line across the head's own pad first
        x0, y0 = PAD_X[t] + 2, PAD_Y + PAD / 2
        job.path([(x0, y0), (x0 + PAD - 4, y0)], LW, speed)
    if t == 0 and layer_idx < 2:
        for (xc, yc) in VERN.values():
            bars(job, main_comb_x(*xc), speed)
            bars(job, main_comb_y(*yc), speed)
    elif t != 0:
        (xc, yc) = VERN[t]
        bars(job, vern_comb_x(*xc), speed)
        bars(job, vern_comb_y(*yc), speed)
        for s in dots(xc[0] - 14.0, xc[1] - BAR - 6.0, t + 1):
            job.path(s, LW, speed)
        for s in dots(yc[0] - 14.0, yc[1] - N - 5.0, t + 1):
            job.path(s, LW, speed)


def build(heads=HEADS):
    mats = {t: records.material(m) for t, m in heads.items()}
    job = Job("P2 head alignment + first-layer pads", mats, layer_height=H,
              first_layer_height=H, line_width=LW,
              notes=["Head 1 = reference spool. Heads 2-4 should contrast with it.",
                     "Keep the screen's filament-to-head mapping 1:1 (T0=head 1 ...)."])
    others = [t for t in sorted(heads) if t != 0]
    plan = [[0] + others, list(reversed(others)) + [0], others]   # layer 1, 2, 3
    job.tool(0)
    for li, order in enumerate(plan):
        job.layer(H * (li + 1), H)
        for t in order:
            print_head(job, t, li)
    return job


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "..", "gcode", "P2_alignment_first_layer.gcode")
    print(build().save(os.path.abspath(out)))
