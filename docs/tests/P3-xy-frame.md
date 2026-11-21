# P3 – 100 mm XY frame

File: `gcode/P3_xy_frame.gcode` (~8 min, ~2.3 g). Reference white PLA in head 1.

A 100 × 100 mm square frame, 1.35 mm walls, 4 mm tall. The little square tab
marks the front-left corner.

## Measure (outside dimensions, calipers)
- X: front edge and back edge
- Y: left edge and right edge
- Diagonal A: front-left corner → back-right corner
- Diagonal B: front-right corner → back-left corner
(141.42 mm nominal; just fits 150 mm calipers.)

## Result
- `scale_x = 100 / mean(X)`, `scale_y = 100 / mean(Y)`
- `skew_deg = degrees(asin((A² − B²) / (4 × X × Y)))`  (≈ degrees((A − B) / 141.4) for small skew)

Reference PLA shrinks about 0.2–0.3 %; we only act on more than that.
Write to `records/printer/u1.yaml → xy_frame`.
