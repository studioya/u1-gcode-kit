# P1 – Extruder feed by weight

File: `gcode/P1_extruder_weight.gcode` (~22 min, ~12 g)
Needs: M0 steps 1–2 done for the spool in each head.

Each head pushes **exactly 500 mm** of filament into free air, twice, circling
30 mm above the bed. Nothing is printed; the strand piles onto the bed.
Defect detection is off on purpose. Keep the screen's filament-to-head mapping
1:1 (filament 1 → head 1 …).

```
            x=45     x=105    x=165    x=225
y=235      prime    prime    prime    prime     <- throw away
y=170      1-B      2-B      3-B      4-B
y=80       1-A      2-A      3-A      4-A       <- front of printer
```

## Read
1. Let the piles cool, lift each one off (snip any thread linking it to the next).
2. Weigh each pile to 0.01 g.

## Result
For each head: `feed_factor = mean(A, B) / (0.5 × linear_density_g_m)`

- 0.99–1.01: leave it; we still record it.
- outside that: the engine divides every E by the factor for that head.
- A and B more than 2 % apart: repeat; something slipped.

Write to `records/printer/u1.yaml → heads.<n>.feed_factor`.
