"""G-code writer for the Snapmaker U1.

The writer owns everything printer-specific: start/end sequences, tool changes,
retraction, layer markers and the metadata footer the U1's Moonraker reads.
Toolpath code (calibration tests, the slicer, parametric generators) only calls
`tool`, `layer`, `travel`, `line_to`, `path` and friends.

Extrusion model: Orca/Slic3r rounded-rectangle bead,
    area = (w - h) * h + pi * (h / 2) ** 2
so a flow ratio measured in Orca and one measured here mean the same thing.
Filament cross-section comes from the spool record: linear density / density
when both were weighed, otherwise the measured (or nominal) diameter.
"""
from __future__ import annotations

import math
import datetime as _dt
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from . import machine as M

KIT_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
@dataclass
class Material:
    """What one head is loaded with. Values normally come from records/materials."""
    name: str = "Generic PLA"
    type: str = "PLA"
    colour: str = "#FFFFFF"
    nozzle_temp: float = 210.0
    first_layer_temp: float = 220.0
    bed_temp: float = 60.0
    first_layer_bed_temp: float = 60.0
    standby_delta: float = -40.0       # temperature while docked and still needed
    flow_ratio: float = 0.98
    density: float = 1.24              # g/cm^3
    diameter: float = 1.75             # mm, measured if known
    linear_density: Optional[float] = None  # g/m, weighed; overrides diameter
    max_volumetric: float = 12.0       # mm^3/s
    retract_length: float = 0.8
    retract_speed: float = 30.0
    fan_min: int = 100
    fan_max: int = 100
    fan_off_layers: int = 1
    chamber: str = "cool"              # cool | weak | warm  (top-cover purifier)
    pressure_advance: Optional[float] = None  # only emitted if set
    soft: bool = False

    @property
    def filament_area(self) -> float:
        """mm^2 of filament cross-section."""
        if self.linear_density:
            # g/m / (g/cm^3) = cm^3/m = 1000 mm^3 / 1000 mm = mm^2
            return self.linear_density / self.density
        return math.pi * (self.diameter / 2) ** 2

    @property
    def grams_per_mm(self) -> float:
        return self.filament_area * self.density / 1000.0


def bead_area(width: float, height: float) -> float:
    if width <= height:
        return math.pi * (width / 2) * (height / 2)
    return (width - height) * height + math.pi * (height / 2) ** 2


# ---------------------------------------------------------------------------
@dataclass
class _ToolState:
    material: Material
    feed_factor: float = 1.0      # actual / commanded filament feed (P1 test)
    retracted: float = 0.0        # mm currently pulled back
    used: bool = False
    e_total: float = 0.0          # commanded filament mm (after feed factor)
    picked_once: bool = False


class Job:
    def __init__(self, title: str, materials: dict[int, Material],
                 feed_factors: Optional[dict[int, float]] = None,
                 bed_type: str = "Textured PEI Plate",
                 defect_detection: bool = True,
                 layer_height: float = 0.2, first_layer_height: float = 0.2,
                 line_width: float = 0.42, outer_wall_speed: float = 60.0,
                 travel_speed: float = M.TRAVEL_SPEED,
                 notes: Sequence[str] = ()):
        for t in materials:
            if t not in M.TOOLS:
                raise ValueError(f"tool {t} does not exist on the U1")
        self.title = title
        self.tools = {t: _ToolState(m, (feed_factors or {}).get(t, 1.0))
                      for t, m in materials.items()}
        self.bed_type = bed_type
        self.defect_detection = defect_detection
        self.layer_height = layer_height
        self.first_layer_height = first_layer_height
        self.line_width = line_width
        self.outer_wall_speed = outer_wall_speed
        self.travel_speed = travel_speed
        self.notes = list(notes)

        self.body: list[str] = []
        self.cur_tool: Optional[int] = None
        self.initial_tool: Optional[int] = None
        self.x = self.y = None
        self.z = 0.0
        self.h = first_layer_height   # current layer thickness
        self.layer_num = -1
        self.hopped = False
        self.bbox = [math.inf, math.inf, -math.inf, -math.inf]
        self.max_z = 0.0
        self.time_s = 0.0
        self.min_travel_retract = 1.0
        self.fan_pct: Optional[int] = None

    # -- low level -------------------------------------------------------
    def emit(self, line: str = ""):
        self.body.append(line)

    def comment(self, text: str):
        for ln in str(text).splitlines():
            self.emit(f"; {ln}")

    @property
    def mat(self) -> Material:
        return self.tools[self.cur_tool].material

    def _feed(self, f_mm_s: float) -> str:
        return f"F{round(f_mm_s * 60)}"

    def _track_xy(self, x, y):
        b = self.bbox
        b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)

    def _move_time(self, dist, speed):
        if speed > 0:
            self.time_s += dist / speed

    # -- tools -----------------------------------------------------------
    def tool(self, t: int):
        if t not in self.tools:
            raise ValueError(f"T{t} has no material assigned in this job")
        if t == self.cur_tool:
            return
        if self.cur_tool is None:
            # First tool: the start sequence picks it up and purges it.
            self.initial_tool = t
            self.cur_tool = t
            st = self.tools[t]
            st.picked_once = True
            st.retracted = 0.0     # start line leaves it primed
            return
        prev = self.cur_tool
        ps = self.tools[prev]
        # Retract the outgoing tool for the dock (Orca retract_length_toolchange)
        extra = M.TOOLCHANGE_RETRACT - ps.retracted
        if extra > 0:
            self._raw_e(-extra, M.RETRACT_SPEED, tool=prev)
            ps.retracted = M.TOOLCHANGE_RETRACT
        # Outgoing tool to standby (it may come back)
        stdby = max(0.0, ps.material.nozzle_temp + ps.material.standby_delta)
        self.emit(f"M104 T{prev} S{stdby:.0f} ; T{prev} standby")
        ns = self.tools[t]
        temp = ns.material.first_layer_temp if self.layer_num <= 0 else ns.material.nozzle_temp
        self.comment(f"Change Tool{prev} -> Tool{t} (layer {self.layer_num})")
        self.emit("G91")
        self.emit(f"G1 Z{M.TOOLCHANGE_LIFT} F600")
        self.emit("G90")
        self.emit(f"G1 F{round(min(self.travel_speed, M.TOOLCHANGE_SPEED) * 60)}")
        self.emit(f"M109 S{temp:.0f} T{t}")
        self.emit("M400")
        self.emit(f"T{t}")
        if t != self.initial_tool and not ns.picked_once:
            # Firmware purges + cuts at the discard station once per print,
            # then leaves the tool 0.5 mm retracted.
            self.emit(f"SM_PRINT_PREEXTRUDE_FILAMENT INDEX={t}")
            ns.retracted = M.PREEXTRUDE_RETRACT
        ns.picked_once = True
        self.emit("G90")
        self.cur_tool = t
        self.z += M.TOOLCHANGE_LIFT
        self.hopped = True
        self.x = self.y = None   # firmware moved the head; position unknown
        self.time_s += M.TOOL_CHANGE_TIME_S + 15.0  # change + reheat estimate
        if self.fan_pct is not None:
            self.fan(self.fan_pct)
        if self.mat.pressure_advance is not None:
            self.emit(f"SET_PRESSURE_ADVANCE EXTRUDER={M.HEATER[t]} "
                      f"ADVANCE={self.mat.pressure_advance:.4f}")

    # -- extrusion primitives -------------------------------------------
    def _raw_e(self, e: float, speed: float, tool: Optional[int] = None):
        t = self.cur_tool if tool is None else tool
        st = self.tools[t]
        e_cmd = e / st.feed_factor
        st.e_total += e_cmd
        self.emit(f"G1 E{e_cmd:.5f} {self._feed(speed)}")
        self._move_time(abs(e), speed)

    def retract(self):
        st = self.tools[self.cur_tool]
        need = self.mat.retract_length - st.retracted
        if need > 1e-6:
            self._raw_e(-need, self.mat.retract_speed)
            st.retracted += need

    def unretract(self):
        st = self.tools[self.cur_tool]
        if st.retracted > 1e-6:
            self._raw_e(st.retracted, M.DERETRACT_SPEED)
            st.retracted = 0.0

    def extrude_only(self, length_mm: float, speed: float):
        """Push filament without moving (filament mm, filament mm/s)."""
        self.unretract()
        remaining = length_mm
        while remaining > 1e-9:
            chunk = min(remaining, M.MAX_EXTRUDE_ONLY_DISTANCE * 0.9)
            self._raw_e(chunk, speed)
            remaining -= chunk
        self.tools[self.cur_tool].used = True

    def extrude_along(self, pts, filament_mm: float, filament_speed: float):
        """Feed an exact filament length while slowly tracing pts (free-air tests).
        XY feed is chosen so the filament feeds at filament_speed mm/s."""
        self.unretract()
        segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs)
        duration = filament_mm / filament_speed
        xy_speed = total / duration
        st = self.tools[self.cur_tool]
        for a, b in segs:
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            e = filament_mm * d / total / st.feed_factor
            st.e_total += e
            self.emit(f"G1 X{b[0]:.3f} Y{b[1]:.3f} E{e:.5f} {self._feed(xy_speed)}")
            self._track_xy(*b)
            self.x, self.y = b
        st.used = True
        self.time_s += duration

    # -- motion ----------------------------------------------------------
    def _goto_z(self, z, speed=M.MAX_Z_VELOCITY):
        if abs(z - self.z) > 1e-6:
            self.emit(f"G1 Z{z:.3f} {self._feed(speed)}")
            self._move_time(abs(z - self.z), speed)
            self.z = z

    def travel(self, x: float, y: float, z: Optional[float] = None, hop: bool = True):
        if not M.bed_contains(x, y):
            raise ValueError(f"travel target ({x:.2f},{y:.2f}) is off the bed")
        target_z = self.layer_z if z is None else z
        dist = math.inf if self.x is None else math.hypot(x - self.x, y - self.y)
        if dist < 1e-6 and abs(target_z - self.z) < 1e-6:
            return
        long_move = dist > self.min_travel_retract
        if long_move:
            self.retract()
            if hop and not self.hopped:
                self._goto_z(self.z + M.Z_HOP)
                self.hopped = True
        self.emit(f"G1 X{x:.3f} Y{y:.3f} {self._feed(self.travel_speed)}")
        if dist != math.inf:
            self._move_time(dist, self.travel_speed)
        self.x, self.y = x, y
        self._goto_z(target_z)
        self.hopped = False

    def line_to(self, x: float, y: float, width: Optional[float] = None,
                speed: float = 40.0, flow: float = 1.0, height: Optional[float] = None):
        if self.x is None:
            raise RuntimeError("line_to before any travel: position unknown")
        if not M.bed_contains(x, y):
            raise ValueError(f"extrusion target ({x:.2f},{y:.2f}) is off the bed")
        w = width or self.line_width
        h = height or self.h
        dist = math.hypot(x - self.x, y - self.y)
        if dist < 1e-6:
            return
        self.unretract()
        m = self.mat
        st = self.tools[self.cur_tool]
        vol = bead_area(w, h) * dist * m.flow_ratio * flow
        # Respect the material's volumetric limit by slowing down.
        vol_rate = bead_area(w, h) * speed
        if vol_rate > m.max_volumetric:
            speed = m.max_volumetric / bead_area(w, h)
        e = vol / m.filament_area / st.feed_factor
        st.e_total += e
        st.used = True
        self.emit(f"G1 X{x:.3f} Y{y:.3f} E{e:.5f} {self._feed(speed)}")
        self._move_time(dist, speed)
        self._track_xy(self.x, self.y)
        self._track_xy(x, y)
        self.x, self.y = x, y

    def path(self, pts: Iterable[tuple[float, float]], width=None, speed=40.0,
             closed=False, flow=1.0):
        pts = list(pts)
        if not pts:
            return
        self.travel(*pts[0])
        for p in pts[1:]:
            self.line_to(p[0], p[1], width, speed, flow)
        if closed:
            self.line_to(pts[0][0], pts[0][1], width, speed, flow)

    def dwell(self, seconds: float):
        self.emit(f"G4 P{int(seconds * 1000)}")
        self.time_s += seconds

    def fan(self, pct: int):
        self.fan_pct = pct
        self.emit(f"M106 S{round(max(0, min(100, pct)) * 2.55)}")

    # -- layers ----------------------------------------------------------
    @property
    def layer_z(self) -> float:
        return self._layer_z if self.layer_num >= 0 else self.z

    def layer(self, z: float, height: Optional[float] = None):
        """Start a new layer whose top is at z."""
        self.layer_num += 1
        self.h = height or (self.first_layer_height if self.layer_num == 0 else self.layer_height)
        self._layer_z = z
        self.max_z = max(self.max_z, z)
        self.emit(";BEFORE_LAYER_CHANGE")
        self.emit(f";{z:.3f}")
        self.emit("G92 E0")
        if self.defect_detection:
            self.emit("DEFECT_DETECTION_DETECT")
        self.emit(";LAYER_CHANGE")
        self.emit(f";Z:{z:.3f}")
        self.emit(f";HEIGHT:{self.h:.3f}")
        if self.cur_tool is not None:
            self.retract()
            self._goto_z(z if not self.hopped else max(z, self.z))
        self.emit(";AFTER_LAYER_CHANGE")
        self.emit(f";{z:.3f}")
        self.emit(f"SET_PRINT_STATS_INFO CURRENT_LAYER={self.layer_num + 1}")
        if self.layer_num == 1 and self.cur_tool is not None:
            m = self.mat
            if m.nozzle_temp != m.first_layer_temp:
                self.emit(f"M104 T{self.cur_tool} S{m.nozzle_temp:.0f}")
            if m.bed_temp != m.first_layer_bed_temp:
                self.emit(f"M140 S{m.bed_temp:.0f}")
        if self.layer_num == 0:
            self.fan(0)
        elif self.layer_num == self.mat.fan_off_layers:
            self.fan(self.mat.fan_max)

    # -- assembly --------------------------------------------------------
    def _mesh_cmd(self) -> str:
        x0, y0, x1, y1 = self.bbox
        pad = 5.0
        x0 = max(M.MESH_MIN, x0 - pad); y0 = max(M.MESH_MIN, y0 - pad)
        x1 = min(M.MESH_MAX, x1 + pad); y1 = min(M.MESH_MAX, y1 + pad)
        nx = max(3, min(13, math.ceil((x1 - x0) / M.MESH_SPACING) + 1))
        ny = max(3, min(13, math.ceil((y1 - y0) / M.MESH_SPACING) + 1))
        off = " Z_OFFSET=-0.07" if self.bed_type == "High Temp Plate" else ""
        return (f"BED_MESH_CALIBRATE mesh_min={x0:.3f},{y0:.3f} mesh_max={x1:.3f},{y1:.3f} "
                f"ALGORITHM=bicubic PROBE_COUNT={nx},{ny} ADAPTIVE=0 ADAPTIVE_MARGIN=0{off}")

    def _start(self) -> list[str]:
        t0 = self.initial_tool
        m0 = self.tools[t0].material
        bed = max(st.material.first_layer_bed_temp for st in self.tools.values())
        chambers = {st.material.chamber for st in self.tools.values()}
        if "warm" in chambers:
            purifier = "SET_PURIFIER_MODE MODE=3 DESIRE_TEMP=45 FAN_SPEED=0.6 DELAY_OFF=600 ; keep warm"
        elif "weak" in chambers:
            purifier = "SET_PURIFIER_MODE MODE=1 DESIRE_TEMP=45 ALARM_TEMP=51 FAN_SPEED=0.6 DELAY_OFF=0 ; weak cooling"
        else:
            purifier = "SET_PURIFIER_MODE MODE=1 DESIRE_TEMP=42 ALARM_TEMP=48 FAN_SPEED=0.6 DELAY_OFF=0 ; strong cooling"
        noz = m0.nozzle_temp
        hp = self.bed_type == "High Temp Plate"
        L = [
            "; ===== U1 start (Snapmaker Orca U1 0.4 start G-code, 20260128) =====",
            "SET_PRINT_AUTO_BED_LEVELING ENABLE=1",
            "PRINT_START",
        ]
        if self.defect_detection:
            L.append("DEFECT_DETECTION_START")
        L += [
            f"SET_PRINT_STATS_INFO TOTAL_LAYER={self.layer_num + 1} CURRENT_LAYER=0",
            f"M140 S{bed:.0f}",
            f"M104 T{t0} S140",
            "M204 S10000",
            purifier,
            "G28 X Y",
        ]
        if self.defect_detection:
            L.append("DEFECT_DETECT_NOODLE_FIRST")
        L += [f"T{t0}", "G90"]
        if self.defect_detection:
            L.append("DEFECT_DETECTION_DETECT_BED")
        L += [
            "SM_PRINT_CHECK_SWITCH_EXTRUDER",
            "; auto feed + dynamic flow (pressure advance) calibration, per used head",
            "SM_PRINT_EXTRUDER_PREHEAT EXTRUDER=1 TEMP=140",
            "SM_PRINT_AUTO_FEED EXTRUDER=0", "SM_PRINT_FLOW_CALIBRATE EXTRUDER=0",
            "SM_PRINT_EXTRUDER_PREHEAT EXTRUDER=2 TEMP=140",
            "SM_PRINT_AUTO_FEED EXTRUDER=1", "SM_PRINT_FLOW_CALIBRATE EXTRUDER=1",
            "SM_PRINT_EXTRUDER_PREHEAT EXTRUDER=3 TEMP=140",
            "SM_PRINT_AUTO_FEED EXTRUDER=2", "SM_PRINT_FLOW_CALIBRATE EXTRUDER=2",
            "SM_PRINT_AUTO_FEED EXTRUDER=3", "SM_PRINT_FLOW_CALIBRATE EXTRUDER=3",
            "M104 S0 T0 A0", "M104 S0 T1 A0", "M104 S0 T2 A0", "M104 S0 T3 A0",
            f"M104 T{t0} S{noz:.0f}",
            f"T{t0}",
            f"M109 T{t0} S{noz:.0f}",
            f"SM_PRINT_PREEXTRUDE_FILAMENT INDEX={t0}",
            f"M104 T{t0} S{noz - 90:.0f}",
            f"T{t0}",
            "M106 S255", "M106 P2 S0",
            "MOVE_TO_DISCARD_FILAMENT_POSITION",
            f"M109 T{t0} S{noz - 90:.0f}",
            "ROUGHLY_CLEAN_NOZZLE_WITH_DISCARD",
            "MOVE_TO_XY_IDLE_POSITION_EXTRUDER",
            "M107",
            "G28 Z I140 J140",
            "M107",
            "DETECT_BED_PLATE",
            "M106 S255", "G90", "G0 Z5 F10000",
            "MOVE_TO_DISCARD_FILAMENT_POSITION",
            f"M109 S{noz - 50:.0f}",
            "ROUGHLY_CLEAN_NOZZLE",
            "MOVE_TO_XY_IDLE_POSITION_EXTRUDER",
            "FINELY_CLEAN_NOZZLE_STAGE_1",
            f"M104 S{noz - 90:.0f}",
            "G0 Z5 F10000",
            "MOVE_TO_DISCARD_FILAMENT_POSITION",
            "ROUGHLY_CLEAN_NOZZLE",
            "MOVE_TO_XY_IDLE_POSITION_EXTRUDER",
            "FINELY_CLEAN_NOZZLE_STAGE_2",
            "M106 S255",
            f"M109 S{noz - 90:.0f}",
            f"M190 S{bed:.0f}",
            "M107 P2", "G90", "G0 Z5 F10000",
            "WAIT_CHAMBER_TEMP TIMEOUT=180",
            "M107",
            "G28 Z Z_OFFSET -0.07" if hp else "G28 Z",
            "M107",
            self._mesh_cmd(),
            "; start line",
            "G90", "G1 Z1.5",
            f"G0 X{M.START_LINE['x0']} Y{M.START_LINE['y']} Z2 F18000",
            f"M109 S{m0.first_layer_temp:.0f}",
            f"G1 Z{M.START_LINE['z']}",
            "M83",
            f"G1 X{M.START_LINE['x1']} E{M.START_LINE['e']} F{M.START_LINE['f']}",
            "G1 Z1.5",
            "G90",
            "M106 S0",
        ]
        # Our own additions: absolute XYZ, relative E, per-head PA override.
        L += ["G90", "M83", "G92 E0"]
        for t, st in self.tools.items():
            if st.material.pressure_advance is not None:
                L.append(f"SET_PRESSURE_ADVANCE EXTRUDER={M.HEATER[t]} "
                         f"ADVANCE={st.material.pressure_advance:.4f}")
        L.append("; ===== end of start =====")
        return L

    def _end(self) -> list[str]:
        L = ["; ===== U1 end (Snapmaker Orca U1 0.4 end G-code, 20260605) ====="]
        if self.cur_tool is not None:
            self.retract()   # lands at the end of the body
        L += [
            "G91", "G1 Z2 F600", "G90",
            "M106 S0",
            "PRINT_END",
            "; filament_volume_type = " + ",".join("standard" for _ in self.tools),
        ]
        return L

    def _footer(self) -> list[str]:
        n = len(M.TOOLS)
        def per_tool(fn, fmt="{:.2f}", sep=", "):
            out = []
            for t in M.TOOLS:
                st = self.tools.get(t)
                out.append(fmt.format(fn(st)) if st else fmt.format(0))
            return sep.join(out)
        used_mm = {t: max(0.0, st.e_total) for t, st in self.tools.items()}
        used_g = {t: used_mm[t] * st.material.grams_per_mm for t, st in self.tools.items()}
        secs = int(self.time_s)
        h, rem = divmod(secs, 3600); mnt, s = divmod(rem, 60)
        est = (f"{h}h " if h else "") + f"{mnt}m {s}s"
        mats = [self.tools[t].material if t in self.tools else None for t in M.TOOLS]
        def mlist(attr, default, sep=";", fmt="{}"):
            return sep.join(fmt.format(getattr(m, attr)) if m else str(default) for m in mats)
        first = self.tools[self.initial_tool].material
        F = [
            f"; filament used [mm] = " + ", ".join(f"{used_mm.get(t, 0):.2f}" for t in M.TOOLS),
            f"; filament used [cm3] = " + ", ".join(
                f"{used_mm.get(t, 0) * self.tools[t].material.filament_area / 1000:.2f}" if t in self.tools else "0.00"
                for t in M.TOOLS),
            f"; filament used [g] = " + ", ".join(f"{used_g.get(t, 0):.2f}" for t in M.TOOLS),
            f"; total filament used [g] = {sum(used_g.values()):.2f}",
            f"; estimated printing time (normal mode) = {est}",
            f"; total layers count = {self.layer_num + 1}",
            "; CONFIG_BLOCK_START",
            "; printer_model = Snapmaker U1",
            f'; printer_settings_id = "Snapmaker U1 (0.4 nozzle)"',
            f"; machine_tool_change_time = {M.TOOL_CHANGE_TIME_S:.0f}",
            f"; printable_area = {M.BED_X_MIN}x{M.BED_Y_MIN},{M.BED_X_MAX}x{M.BED_Y_MIN},"
            f"{M.BED_X_MAX}x{M.BED_Y_MAX},{M.BED_X_MIN}x{M.BED_Y_MAX}",
            f"; printable_height = {M.MAX_Z + 0.05:.2f}",
            f"; filament_type = " + mlist("type", "PLA"),
            f"; filament_colour = " + mlist("colour", "#FFFFFF"),
            f"; filament_settings_id = " + ";".join(f'"{m.name}"' if m else '""' for m in mats),
            f"; filament_diameter = " + mlist("diameter", 1.75, ","),
            f"; filament_flow_ratio = " + mlist("flow_ratio", 0.98, ","),
            f"; filament_max_volumetric_speed = " + mlist("max_volumetric", 12, ","),
            f"; nozzle_temperature = " + mlist("nozzle_temp", 210, ",", "{:.0f}"),
            f"; first_layer_temperature = " + mlist("first_layer_temp", 220, ",", "{:.0f}"),
            f"; first_layer_bed_temperature = {first.first_layer_bed_temp:.0f}",
            f"; nozzle_diameter = " + ",".join(f"{M.NOZZLE}" for _ in M.TOOLS),
            f"; layer_height = {self.layer_height}",
            f"; first_layer_height = {self.first_layer_height}",
            f"; line_width = {self.line_width}",
            f"; outer_wall_speed = " + ",".join(f"{self.outer_wall_speed:.0f}" for _ in M.TOOLS),
            f"; outer_wall_acceleration = " + ",".join("5000" for _ in M.TOOLS),
            f"; filament_retract_length_toolchange = " + ",".join(f"{M.TOOLCHANGE_RETRACT:.0f}" for _ in M.TOOLS),
            f"; print_sequence = by layer",
            f"; curr_bed_type = {self.bed_type}",
            "; CONFIG_BLOCK_END",
        ]
        return F

    def render(self) -> str:
        if self.initial_tool is None:
            raise RuntimeError("job never selected a tool")
        end = self._end()  # may emit a final retract into body
        now = _dt.datetime.now().strftime("%Y-%m-%d at %H:%M:%S")
        head = [
            f"; generated by u1-gcode-kit {KIT_VERSION} - metadata written in "
            f"OrcaSlicer 2.3.1 on {now} format so the U1 reads it",
            f"; job: {self.title}",
        ] + [f"; note: {n}" for n in self.notes] + [
            "; HEADER_BLOCK_START",
            f"; total layer number: {self.layer_num + 1}",
            f"; max_z_height: {self.max_z:.2f}",
            "; HEADER_BLOCK_END",
            "",
        ]
        lines = head + self._start() + self.body + end + [""] + self._footer()
        return "\n".join(lines) + "\n"

    def save(self, path: str) -> str:
        txt = self.render()
        with open(path, "w") as f:
            f.write(txt)
        return path
