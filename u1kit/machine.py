"""Snapmaker U1 machine facts.

Every value here comes from Snapmaker's own sources, pinned so we can re-check
them when firmware changes:
  - Orca profile:  OrcaSlicer/OrcaSlicer resources/profiles/Snapmaker/machine/
                   "fdm_U1.json" and "Snapmaker U1 (0.4 nozzle).json"
                   (start G-code dated 20260128, tool change 20260607, end 20260605)
  - Firmware:      Snapmaker/u1-klipper lava/printer.cfg, lava/fluidd.cfg,
                   klippy/extras/print_stats.py, print_task_config.py
  - Metadata:      Snapmaker/u1-moonraker moonraker/components/file_manager/metadata.py
Measured values for *this* printer live in records/printer/u1.yaml, not here.
"""

# --- Geometry (Orca printable_area / printable_height) ---------------------
BED_X_MIN, BED_X_MAX = 0.5, 270.5
BED_Y_MIN, BED_Y_MAX = 1.0, 271.0
MAX_Z = 270.0
# Keep our own toolpaths a little inside the printable area.
SAFE_MARGIN = 3.0
# Bed-mesh probing limits (printer.cfg [bed_mesh])
MESH_MIN, MESH_MAX = 3.0, 267.0
MESH_SPACING = 22.0  # 13 x 13 over 264 mm

# --- Motion limits (printer.cfg [printer], Orca machine limits) ------------
MAX_VELOCITY = 500.0       # mm/s
MAX_ACCEL = 20000.0        # mm/s^2
MAX_Z_VELOCITY = 20.0      # Orca limit (firmware allows 30)
MAX_E_VELOCITY = 30.0      # mm/s of filament
MAX_EXTRUDE_ONLY_DISTANCE = 200.0  # mm per extrude-only move (printer.cfg)
MIN_EXTRUDE_TEMP = 170.0
MAX_NOZZLE_TEMP = 300.0

# --- Toolheads --------------------------------------------------------------
TOOLS = (0, 1, 2, 3)          # G-code tools T0..T3 = heads 1..4 on the screen
HEATER = {0: "extruder", 1: "extruder1", 2: "extruder2", 3: "extruder3"}
NOZZLE = 0.4
FILAMENT_DIAMETER = 1.75
FACTORY_ROTATION_DISTANCE = 4.95  # printer.cfg [extruder]

# --- Orca U1 0.4 defaults we copy ---------------------------------------
TOOLCHANGE_RETRACT = 10.0     # retract_length_toolchange
TOOLCHANGE_LIFT = 1.5         # relative Z lift in change_filament_gcode
TOOLCHANGE_SPEED = 350.0      # max_speed_toolchange (mm/s)
PREEXTRUDE_RETRACT = 0.5      # INNER_PREEXTRUDE_FILAMENT leaves the tool 0.5 mm retracted
Z_HOP = 0.4
RETRACT_SPEED = 30.0
DERETRACT_SPEED = 30.0
TRAVEL_SPEED = 300.0
TOOL_CHANGE_TIME_S = 5.0      # machine_tool_change_time

# Start purge line drawn by the stock start G-code (X85 -> X185 at Y1, E15)
START_LINE = dict(x0=85.0, x1=185.0, y=1.0, z=0.2, e=15.0, f=360)


def bed_contains(x, y, margin=0.0):
    return (BED_X_MIN + margin <= x <= BED_X_MAX - margin and
            BED_Y_MIN + margin <= y <= BED_Y_MAX - margin)
