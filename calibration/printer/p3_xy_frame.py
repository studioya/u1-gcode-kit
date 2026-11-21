"""P3 - 100 mm XY frame for scale and skew (printer layer).

A 100 x 100 mm square frame, 3 lines wide, 4 mm tall, printed with the
reference spool on head 1. Small corner tabs mark the front-left corner.

Measure with calipers (all outside dimensions):
  outer X (front edge and back edge), outer Y (left and right edge),
  diagonal A front-left -> back-right, diagonal B front-right -> back-left.

  scale_x = 100 / mean(outer X)        scale_y = 100 / mean(outer Y)
  skew (deg) = degrees(asin((A^2 - B^2) / (4 * X * Y)))

Shrinkage of the reference PLA is ~0.2-0.3 %, so we only act on scale errors
bigger than that; anything material-specific is measured later with the
check coupon (M-layer), not here.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from u1kit import records, shapes  # noqa: E402
from u1kit.writer import Job  # noqa: E402

REFERENCE = "white-pla"
SIZE = 100.0
LINES = 3
LW = 0.45
H = 0.2
HEIGHT = 4.0
X0, Y0 = 85.0, 85.0      # front-left outside corner -> frame centred on the bed


def build():
    job = Job("P3 100 mm XY frame", {0: records.material(REFERENCE)},
              feed_factors=records.feed_factors(), layer_height=H,
              first_layer_height=H, line_width=LW)
    job.tool(0)
    n_layers = int(round(HEIGHT / H))
    loops = shapes.inset_loops(X0, Y0, X0 + SIZE, Y0 + SIZE, LINES, LW)
    for li in range(n_layers):
        job.layer(H * (li + 1), H)
        speed = 25.0 if li == 0 else 50.0
        # inner loops first, outer wall last (same order as Orca's default)
        for loop in reversed(loops):
            # start every loop at its front-left corner so seams stack in one place
            job.path(loop, LW, speed, closed=True)
        if li < 3:
            # orientation tab outside the front-left corner (first 3 layers only)
            job.path(shapes.rect_loop(X0 - 6, Y0 - 6, X0 - 2, Y0 - 2), LW, speed, closed=True)
    return job


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "..", "gcode", "P3_xy_frame.gcode")
    print(build().save(os.path.abspath(out)))
