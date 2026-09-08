"""Builder for bar charts (image-reconstruction use case — see bar.md)."""
from svgkit import geometry as g, gradients as grad, text, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    p = cfg["plot"]
    ymin, ymax = cfg["y_axis"]["min"], cfg["y_axis"]["max"]
    ticks = cfg["y_axis"].get("ticks", 5)
    horiz = cfg.get("orientation") == "horizontal"
    corner = cfg.get("corner", 4)
    font = cfg.get("font", {})
    defs, body = [], []

    def y_of(v):
        return p["y"] + p["h"] * (1 - (v - ymin) / (ymax - ymin))

    def x_of(v):
        return p["x"] + p["w"] * ((v - ymin) / (ymax - ymin))

    if cfg.get("grid", True):
        for i in range(ticks + 1):
            val = ymin + (ymax - ymin) * i / ticks
            if horiz:
                gx = x_of(val)
                body.append(f'<line x1="{gx:.1f}" y1="{p["y"]}" x2="{gx:.1f}" '
                            f'y2="{p["y"]+p["h"]}" stroke="{presets.RULE}"/>')
                body.append(text.label(gx, p["y"]+p["h"]+20, f"{val:g}",
                            font.get("axis_size", 13), color="#666", weight="400"))
            else:
                gy = y_of(val)
                body.append(f'<line x1="{p["x"]}" y1="{gy:.1f}" '
                            f'x2="{p["x"]+p["w"]}" y2="{gy:.1f}" stroke="{presets.RULE}"/>')
                body.append(text.label(p["x"]-14, gy, f"{val:g}",
                            font.get("axis_size", 13), color="#666",
                            weight="400", anchor="end"))

    bars = cfg["bars"]
    n = len(bars)
    gap_ratio = cfg.get("bar_gap_ratio", 0.35)
    slot = (p["h"] if horiz else p["w"]) / n
    bw = slot * (1 - gap_ratio)

    for i, b in enumerate(bars):
        gid = f"bar{i}"
        defs.append(grad.linear(gid, b.get("gradient_angle", 90 if not horiz else 0),
                                b["stops"]))
        if horiz:
            by = p["y"] + slot * i + (slot - bw) / 2
            bx = p["x"]
            length = x_of(b["value"]) - p["x"]
            body.append(f'<path d="{g.rounded_rect(bx, by, length, bw, corner)}" '
                        f'fill="url(#{gid})"/>')
            body.append(text.label(p["x"]-14, by+bw/2, b["label"],
                        font.get("label_size", 15), color="#333",
                        weight="600", anchor="end"))
            if cfg.get("value_labels", True):
                body.append(text.label(bx+length+8, by+bw/2, f'{b["value"]:g}',
                            font.get("axis_size", 13), color="#333",
                            weight="600", anchor="start"))
        else:
            bx = p["x"] + slot * i + (slot - bw) / 2
            top = y_of(b["value"])
            h = p["y"] + p["h"] - top
            body.append(f'<path d="{g.rounded_rect(bx, top, bw, h, corner)}" '
                        f'fill="url(#{gid})"/>')
            body.append(text.label(bx+bw/2, p["y"]+p["h"]+24, b["label"],
                        font.get("label_size", 15), color="#333", weight="600"))
            if cfg.get("value_labels", True):
                body.append(text.label(bx+bw/2, top-12, f'{b["value"]:g}',
                            font.get("axis_size", 13), color="#333", weight="600"))

    body.append(f'<line x1="{p["x"]}" y1="{p["y"]+p["h"]}" x2="{p["x"]+p["w"]}" '
                f'y2="{p["y"]+p["h"]}" stroke="#333"/>')
    body.append(f'<line x1="{p["x"]}" y1="{p["y"]}" x2="{p["x"]}" '
                f'y2="{p["y"]+p["h"]}" stroke="#333"/>')

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
