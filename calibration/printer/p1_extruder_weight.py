"""P1 - Extruder feed by weight (printer layer).

Each head pushes exactly 500 mm of filament into free air, twice, while the
nozzle circles slowly 30 mm above the bed. The strand coils onto the bed as a
small pile. Weigh each pile on the 0.01 g scale and compare with the weighed
grams-per-metre of that head's spool (M0):

    feed_factor = pile_mass_g / (500 mm * linear_density_g_m / 1000)

A feed factor of 1.000 means the head pushes exactly what it is told.
The writer divides every E value by this factor, so no firmware edit is needed.

Layout (seen from the front of the printer):
    back row  y=170  : trial B   head1 head2 head3 head4
    front row y=80   : trial A   head1 head2 head3 head4
    x = 45, 105, 165, 225 ;  prime piles (throw away) at y=235
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from u1kit import records, shapes  # noqa: E402
from u1kit.writer import Job  # noqa: E402

HEADS = {0: "white-pla", 1: "clear-pla", 2: "white-abs", 3: "yellow-pla"}
LENGTH = 500.0       # filament mm per pile (~1.5 g PLA: 0.01 g scale -> 0.7 % resolution)
PRIME = 15.0         # filament mm into the throw-away pile first
Z_FREE = 30.0
XS = {0: 45.0, 1: 105.0, 2: 165.0, 3: 225.0}
Y_TRIAL = {"A": 80.0, "B": 170.0}
Y_PRIME = 235.0


def build(heads=HEADS):
    mats = {t: records.material(m) for t, m in heads.items()}
    job = Job("P1 extruder feed by weight", mats, defect_detection=False,
              notes=["Free-air extrusion piles - no part is printed.",
                     "Defect detection is off on purpose: the piles look like spaghetti.",
                     "Keep the screen's filament-to-head mapping 1:1 (T0=head 1 ...)."])
    job.min_travel_retract = 0.5
    order = sorted(heads)
    job.tool(order[0])
    job.layer(Z_FREE, height=0.2)
    job.fan(100)
    for t in order:
        job.tool(t)
        m = job.mat
        # filament mm/s at 75 % of the material volumetric limit
        fspeed = min(5.0, 0.75 * m.max_volumetric / m.filament_area)
        job.comment(f"--- head {t + 1} ({m.name}) prime pile ---")
        job.travel(XS[t], Y_PRIME, z=Z_FREE)
        job.extrude_along(shapes.circle(XS[t], Y_PRIME, 6, 24) + [(XS[t] + 6, Y_PRIME)], PRIME, fspeed)
        job.dwell(2)
        for trial in ("A", "B"):
            cx, cy = XS[t], Y_TRIAL[trial]
            job.comment(f"--- head {t + 1} trial {trial}: exactly {LENGTH:.0f} mm filament ---")
            job.travel(cx + 10, cy, z=Z_FREE)
            # slow laps of a 10 mm radius circle
            ring = shapes.circle(cx, cy, 10, 36)
            pts = (ring * 4) + [ring[0]]
            job.extrude_along(pts, LENGTH, fspeed)
            job.dwell(3)          # let the strand stop oozing before breaking it off
            job.retract()
    return job


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "..", "gcode", "P1_extruder_weight.gcode")
    print(build().save(os.path.abspath(out)))
