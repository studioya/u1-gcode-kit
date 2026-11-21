# U1 calibration program

What we measure, in what order, and where each number ends up. The G-code skill
reads `records/`; it never guesses a value that one of these tests can measure.

Tools on hand: calipers, a 0.01 g scale, phone camera (photos go to Claude).

## Four layers

| Layer | Depends on | Redo when | Lives in |
|---|---|---|---|
| **P – Printer** | the machine | moving the printer, new feet/hood, nozzle or head swap, a crash, firmware update | `records/printer/u1.yaml` |
| **M – Material** | material + brand + colour (+ lot) | new material, new supplier, new lot that prints differently | `records/spools/`, `records/materials/` |
| **X – Material pairs** | two materials in one print | first time a pair shares a print | `records/pairs/` |
| **J – Job settings** | the object | every print | chosen by the skill, inside the limits above |

Printer tests are always judged with the **reference spool** (white PLA, head 1)
so machine error is never mixed up with material behaviour.

## P – Printer

| # | Test | Measures | Tool | Status |
|---|---|---|---|---|
| P0 | Built-in: home & leveling, vibration compensation, toolhead offset | factory routines on the screen | printer | startup only. **Re-run vibration compensation** now that it sits on the cabinet |
| P1 | Extruder feed by weight | per-head feed factor (actual / commanded filament) | scale | file ready |
| P2 | Alignment verniers + first-layer pads | XY offset of heads 2-4 vs head 1 (0.05 mm), Z/first layer per head | eye, calipers | file ready |
| P3 | 100 mm XY frame | X/Y scale, skew | calipers | file ready |
| P4 | Tool-change prime & ooze | blob/gap after a change, docked ooze | eye, scale | next |

The U1's own *Dynamic Flow Calibration* only sets pressure advance, per head and
per loaded material, and forgets it on unload. We read the K values from the
Fluidd console and store them per material (M-layer), so the skill can pin them.

## M – Material (the new-material kit)

Run in order; each step uses the result of the one before.

| # | Step | Measures | Tool | Full kit | Quick kit |
|---|---|---|---|---|---|
| M0 | Spool log | diameter (5 points), **grams per metre** (1 m piece), **density** (Archimedes), moisture (mass before/after drying) | calipers, scale | ✓ | ✓ |
| M1 | Temperature tower | print temperature window | eye | ✓ | |
| M2 | Max flow ramp | volumetric limit (mm³/s) | eye | ✓ | |
| M3 | Flow ratio patches | top-surface flow ratio | eye, photo | ✓ | ✓ |
| M4 | Pressure advance | K per head (pattern test + the printer's dynamic value) | eye, Fluidd | ✓ | ✓ |
| M5 | Retraction | length / speed | eye | ✓ | |
| M6 | Cooling, overhangs, bridges | fan %, overhang angle limit, bridge flow | eye | ✓ | |
| M7 | Check coupon | XY/Z shrink, hole compensation, sliding/press fit clearances, mass check | calipers, scale | ✓ | ✓ |

**Full kit** for a new material type. **Quick kit** for a known material from a new brand or lot.

Why the scale matters: grams-per-metre divided by density gives the filament's
real cross-section, which is more accurate than calipers on a slightly oval
filament. With P1's per-head feed factor, the engine then pushes the right
volume of plastic before any visual flow tuning; M3 is left to fine-tune the
surface, not to correct a wrong diameter.

## X – Material pairs (tool changer)

| # | Test | Measures |
|---|---|---|
| X1 | Interface peel bar | how well A bonds to B (none / weak / ok / strong) |
| X2 | Swap prime ladder | prime after a change, standby ooze at a given standby temperature |

The lampshade test rings coming apart is the kind of failure X1 is for.

## How the skill uses this

One engine for every object (`u1kit/`):
- `writer.py` – everything printer-specific: Snapmaker's start/end/tool-change
  sequences, retraction, layer markers, the metadata footer the U1 reads,
  per-head feed factors, per-material settings.
- toolpath sources on top of it: calibration tests (now), parametric/path-native
  designs (lampshade-style), and a mesh slicer for ordinary solids (walls,
  infill, top/bottom skins, then supports) - to be built after the kit.
- every file is re-checked by `tools/check_gcode.py`, then opened in the U1 viewer.
