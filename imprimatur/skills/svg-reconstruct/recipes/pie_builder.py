"""Builder for pie charts."""
import math
from svgkit import geometry as g, gradients as grad, text, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    cx, cy = cfg["center"]
    R = cfg["radius"]
    total = sum(s["value"] for s in cfg["slices"])
    ang = cfg.get("start_angle", 0)
    defs, body = [], []
    mode = cfg.get("labels", "inside")

    for i, s in enumerate(cfg["slices"]):
        sweep = 360 * s["value"] / total
        start, end = ang, ang + sweep
        mid = (start + end) / 2
        ex = s.get("explode", 0)
        ox, oy = (g.polar(0, 0, ex, mid) if ex else (0, 0))
        ccx, ccy = cx + ox, cy + oy

        gid = f"pie{i}"
        # "color" is an explicit flat-fill choice (respected as-is); with neither
        # "stops" nor "color" given, default to a real per-slice gradient instead
        # of an implicit flat fill — see presets.sequential_stops.
        if "stops" in s or "color" not in s:
            stops = s.get("stops") or presets.sequential_stops(i, len(cfg["slices"]))
            defs.append(grad.linear(gid, s.get("gradient_angle", 135), stops))
            fill = f"url(#{gid})"
        else:
            fill = s["color"]
        body.append(f'<path d="{g.arc_segment(ccx, ccy, 0, R, start, end)}" '
                    f'fill="{fill}"/>')

        if mode != "none":
            pct = f' {100*s["value"]/total:.0f}%' if cfg.get("show_percent") else ""
            if mode == "inside":
                lx, ly = g.polar(ccx, ccy, R*0.6, mid)
                body.append(text.label(lx, ly, s["label"]+pct, 16,
                            color=s.get("label_color", "#fff"), weight="700"))
            else:
                lx, ly = g.polar(ccx, ccy, R+30, mid)
                anchor = "start" if math.cos(math.radians(mid-90)) >= 0 else "end"
                body.append(text.label(lx, ly, s["label"]+pct, 15,
                            color="#333", weight="600", anchor=anchor))
        ang = end

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
