# P2 – Head alignment + first-layer pads

File: `gcode/P2_alignment_first_layer.gcode` (~11 min, ~1 g)
Load: head 1 = reference white PLA; heads 2–4 = PLA in colours that stand out
against white (swap head 3's ABS for any PLA colour for this test).

## Layout
```
y≈205   [pad h1]  [pad h2]  [pad h3]  [pad h4]       20 x 20 mm, 2 layers

y≈150   X-vernier h2   X-vernier h3   X-vernier h4    bars stand upright
y≈95    Y-vernier h2   Y-vernier h3   Y-vernier h4    bars lie sideways
         (dots under each vernier = head number)
```
Head 1 prints the comb with bars every 1.00 mm; the other head prints the comb
with bars every 0.95 mm, butting against it. The long bar is index 0, medium
bars are ±5 and ±10.

## Read the verniers (loupe or phone macro photo helps)
Find the pair of bars that line up best and count its index *i* from the long bar:
- X vernier: + to the right → `dx = +0.05 × i` mm
- Y vernier: + toward the back → `dy = +0.05 × i` mm

That is where head N prints relative to head 1. If it's between two indices,
give half steps (e.g. 2.5 → 0.125 mm). Anything within ±0.05 mm is good.

## Read the pads
Calipers on each pad: centre + 4 corners. Target 0.40 mm.
Also say how the top looks: gaps between lines (too high) / ridges and
shiny smearing (too low).

## Result
`records/printer/u1.yaml → heads.<n>.xy_vs_head1_mm: [dx, dy]`, `z_check_mm`.
If a head is off by more than 0.1 mm, re-run the printer's Multi-toolhead
Offset Calibration and print P2 again before touching anything by hand.
