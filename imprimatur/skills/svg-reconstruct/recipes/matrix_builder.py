"""Builder for 2x2 quadrant matrices."""
from svgkit import geometry as g, text, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    ox, oy = cfg["origin"]; size = cfg["size"]; half = size/2
    q = cfg["quadrants"]  # [TL, TR, BL, BR] each {label, color}
    defs, body = [], []

    coords = [(ox, oy), (ox+half, oy), (ox, oy+half), (ox+half, oy+half)]
    for i, (qx, qy) in enumerate(coords):
        body.append(f'<path d="{g.rounded_rect(qx+2, qy+2, half-4, half-4, 10)}" '
                    f'fill="{q[i].get("color",presets.TINT)}"/>')
        body.append(text.label(qx+half/2, qy+30, q[i]["label"], 16,
                    color="#333", weight="700"))

    for it in cfg.get("items", []):
        px = ox + it["x"] * size
        py = oy + (1 - it["y"]) * size
        body.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{it.get("r",8)}" '
                    f'fill="{it.get("color",presets.PRIMARY)}"/>')
        if it.get("label"):
            body.append(text.label(px+12, py, it["label"], 12, color="#333",
                        weight="500", anchor="start"))

    body.append(text.label(ox+half, oy+size+30, cfg["x_axis"], 14,
                color="#555", weight="600"))
    body.append(text.label(ox-30, oy+half, cfg["y_axis"], 14, color="#555",
                weight="600", rotate=-90))

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
