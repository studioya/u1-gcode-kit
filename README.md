# u1-gcode-kit

G-code engine, calibration kit and measured records for a Snapmaker U1
(4 heads, 0.4 mm nozzles). Every file it makes is checked by
`tools/check_gcode.py` and then opened in
[u1-gcode-viewer](https://github.com/studioya/u1-gcode-viewer) before printing.

```
u1kit/            the engine
  machine.py      U1 facts from Snapmaker's own profile and firmware (sources inside)
  writer.py       start/end/tool-change, retraction, layers, metadata footer
  records.py      loads records/ into the writer
  shapes.py       small path helpers
calibration/
  printer/        P-layer test generators
  material/       M-layer test generators (next)
records/
  printer/u1.yaml measured machine values
  spools/         one file per physical spool (M0)
  materials/      tuned settings per material, status provisional -> calibrated
  pairs/          two materials in one print
gcode/            generated test files, ready to send
docs/
  calibration-program.md   the plan: layers, order, what goes where
  tests/                   one measuring sheet per test
tools/check_gcode.py       independent checker + top-down preview
```

Regenerate a test: `python3 calibration/printer/p2_alignment.py`
Check a file: `python3 tools/check_gcode.py gcode/P2_alignment_first_layer.gcode --png p2.png`

Files carry an Orca-style metadata footer so the U1's Moonraker can read which
heads are used, filament weights and temperatures. The header says plainly that
the file comes from this kit.

MIT licence.
