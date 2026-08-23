"""Builder for horizontal timelines."""
from svgkit import text, icons, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    y = cfg["axis_y"]
    x0, x1 = cfg["start_x"], cfg["end_x"]
    events = cfg["events"]
    body = []

    body.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" '
                f'stroke="{cfg.get("line_color",presets.PRIMARY)}" '
                f'stroke-width="{cfg.get("line_width",4)}" stroke-linecap="round"/>')

    n = len(events)
    for i, e in enumerate(events):
        ex = x0 + (x1 - x0) * (i / max(n-1, 1))
        color = e.get("color", presets.PRIMARY)
        side = e.get("side", "top" if i % 2 == 0 else "bottom")
        dir_ = -1 if side == "top" else 1
        cy = y + dir_ * 70

        body.append(f'<line x1="{ex}" y1="{y}" x2="{ex}" y2="{cy}" '
                    f'stroke="{color}" stroke-width="2"/>')
        body.append(f'<circle cx="{ex}" cy="{y}" r="10" fill="#fff" '
                    f'stroke="{color}" stroke-width="3"/>')
        if e.get("icon"):
            body.append(icons.place(e["icon"], ex, cy + dir_*20, 22, color=color))
        ty = cy + dir_ * 40
        body.append(text.label(ex, ty, e["date"], 15, color=color, weight="700"))
        body.append(text.label(ex, ty + dir_*22, e["title"], 14,
                    color="#333", weight="600"))
        if e.get("desc"):
            body.append(text.label(ex, ty + dir_*42, e["desc"], 11,
                        color="#777", weight="400"))

    doc = canvas.svg(cfg["width"], cfg["height"], "", "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
