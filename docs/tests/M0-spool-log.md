# M0 – Spool log (no printing)

For every spool used in a test. Results go in `records/spools/<id>.yaml`.

## 1. Diameter
Calipers, 5 places along a metre, turning 90° between readings. Write all of them.

## 2. Grams per metre (needed for P1)
1. Straighten and cut a **1000 mm** piece (tape measure; ±1 mm is fine).
2. Weigh it: `sample_mass_g` (PLA ≈ 2.98 g, ABS ≈ 2.50 g).
3. `linear_density_g_m = sample_mass_g / sample_length_mm × 1000`

Keep the piece for step 3.

## 3. Density (Archimedes)
1. Put a cup of water on the scale, add a drop of dish soap, tare.
2. Coil the same piece and hang it on a thin thread so it is fully under water
   without touching the cup. Knock off any bubbles.
   (ABS floats – hold it under with a thin wire tip.)
3. The reading is the mass of displaced water: `submerged_reading_g`.
4. `density = sample_mass_g / submerged_reading_g × 0.997`

## 4. Moisture (optional, when drying)
Weigh the whole spool before and after drying; write both and the dryer settings.

Send me the numbers (or a photo of your notes) and I'll fill the record.
