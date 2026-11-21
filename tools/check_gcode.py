"""Independent checker for U1 G-code made by the kit (or anything Orca-like).

Re-reads the file from scratch - it does not import the writer - and checks:
  * printer start/end blocks present, tool changes heat the next tool first
  * every extruding move is on the bed and above Z 0
  * no extrusion from a tool colder than 170 C
  * volumetric rate per move under the filament limit in the footer
  * per-tool filament totals agree with the footer the U1 reads
Optionally draws a top-down preview PNG coloured by tool.

usage: python3 tools/check_gcode.py file.gcode [--png out.png]
"""
import math
import re
import sys

BED = (0.5, 270.5, 1.0, 271.0)
MIN_TEMP = 170.0


def parse_footer(lines):
    meta = {}
    for ln in lines[-80:]:
        m = re.match(r";\s*([^=]+?)\s*=\s*(.*)$", ln)
        if m:
            meta[m.group(1).strip()] = m.group(2).strip()
    return meta


def floats(s, sep=","):
    return [float(x) for x in re.split(r"[;,]\s*", s) if x.strip() not in ("", '""')]


def check(path, png=None):
    with open(path) as f:
        lines = f.read().splitlines()
    meta = parse_footer(lines)
    errors, warns = [], []
    maxvol = floats(meta.get("filament_max_volumetric_speed", "12,12,12,12"))
    diam = floats(meta.get("filament_diameter", "1.75,1.75,1.75,1.75"))
    footer_mm = floats(meta.get("filament used [mm]", "0,0,0,0"))

    for need in ("PRINT_START", "PRINT_END", "BED_MESH_CALIBRATE", "G28 Z"):
        if not any(l.startswith(need) for l in lines):
            errors.append(f"missing {need}")

    tool = None
    temps = {}
    heated_before_change = set()
    x = y = z = 0.0
    e_body = [0.0] * 4
    in_body = False
    relative_e = False
    layers = 0
    max_rate = [0.0] * 4
    segs = {0: [], 1: [], 2: [], 3: []}
    changes = 0
    feed = 1000.0
    h_layer = 0.2
    for n, raw in enumerate(lines, 1):
        ln = raw.split(";", 1)[0].strip()
        if raw.startswith("; ===== end of start"):
            in_body = True
        if raw.startswith(";HEIGHT:"):
            h_layer = float(raw.split(":")[1])
        if raw.startswith(";LAYER_CHANGE"):
            layers += 1
        if not ln:
            continue
        w = ln.split()
        cmd = w[0]
        args = {a[0]: a[1:] for a in w[1:] if a and a[0].isalpha()}
        if cmd in ("M104", "M109"):
            t = int(args["T"]) if "T" in args else tool
            if "S" in args and t is not None:
                temps[t] = float(args["S"])
                if cmd == "M109":
                    heated_before_change.add(t)
        elif cmd == "M83":
            relative_e = True
        elif cmd == "M82":
            relative_e = False
        elif re.fullmatch(r"T\d", cmd):
            t = int(cmd[1])
            if in_body and t != tool:
                changes += 1
                if t not in heated_before_change:
                    errors.append(f"line {n}: T{t} picked up without M109 for it")
                heated_before_change.discard(t)
            tool = t
        elif cmd in ("G0", "G1"):
            if "F" in args:
                feed = float(args["F"]) / 60.0
            nx = float(args["X"]) if "X" in args else x
            ny = float(args["Y"]) if "Y" in args else y
            nz = float(args["Z"]) if "Z" in args else z
            e = float(args["E"]) if "E" in args else 0.0
            if not relative_e and "E" in args and in_body:
                warns.append(f"line {n}: absolute E in body")
            d = math.hypot(nx - x, ny - y)
            if in_body and tool is not None:
                e_body[tool] += e
                if e > 0:
                    if temps.get(tool, 0) < MIN_TEMP:
                        errors.append(f"line {n}: T{tool} extrudes at {temps.get(tool, 0)} C")
                    if d > 0:
                        if not (BED[0] <= nx <= BED[1] and BED[2] <= ny <= BED[3]):
                            errors.append(f"line {n}: extrusion off the bed at ({nx},{ny})")
                        if nz <= 0:
                            errors.append(f"line {n}: extrusion at Z {nz}")
                        area = math.pi * (diam[tool] / 2) ** 2
                        rate = e * area / (d / feed)
                        max_rate[tool] = max(max_rate[tool], rate)
                        segs[tool].append((x, y, nx, ny))
            x, y, z = nx, ny, nz
    for t in range(4):
        if max_rate[t] > maxvol[t] * 1.01 and e_body[t] > 0:
            errors.append(f"T{t} peaks at {max_rate[t]:.1f} mm3/s > limit {maxvol[t]}")
        if abs(e_body[t] - footer_mm[t]) > 0.5:
            errors.append(f"T{t}: body E {e_body[t]:.2f} mm vs footer {footer_mm[t]:.2f} mm")
    declared = int(meta.get("total layers count", -1))
    if declared != layers:
        errors.append(f"footer says {declared} layers, file has {layers}")

    used = [t for t in range(4) if e_body[t] > 0]
    print(f"{path}")
    print(f"  tools used: {['T%d' % t for t in used]}  tool changes: {changes}  layers: {layers}")
    print(f"  filament mm: {[round(v, 2) for v in e_body]}  (footer {footer_mm})")
    print(f"  filament g : {meta.get('filament used [g]')}  time: {meta.get('estimated printing time (normal mode)')}")
    print(f"  peak mm3/s : {[round(v, 1) for v in max_rate]}")
    for w_ in warns[:5]:
        print("  WARN", w_)
    for e_ in errors[:20]:
        print("  ERROR", e_)
    print("  OK" if not errors else f"  {len(errors)} error(s)")

    if png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import LineCollection
        cols = meta.get("filament_colour", "#000;#000;#000;#000").split(";")
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.set_facecolor("#3a3a3a")
        for t, ss in segs.items():
            if ss:
                c = cols[t] if t < len(cols) else "#ffffff"
                ax.add_collection(LineCollection([((a, b), (c_, d)) for a, b, c_, d in ss],
                                                 colors=c, linewidths=0.6, label=f"head {t + 1}"))
        ax.set_xlim(0, 271); ax.set_ylim(0, 272); ax.set_aspect("equal")
        ax.legend(loc="upper right", fontsize=8)
        ax.set_title(path.split("/")[-1], fontsize=9)
        fig.savefig(png, dpi=150, bbox_inches="tight")
    return not errors


if __name__ == "__main__":
    png = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
    ok = check(sys.argv[1], png)
    sys.exit(0 if ok else 1)
