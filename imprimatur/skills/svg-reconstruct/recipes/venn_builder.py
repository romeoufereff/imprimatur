"""Builder for Venn diagrams."""
from svgkit import text, canvas, schema


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    body = []
    for c in cfg["circles"]:
        body.append(f'<circle cx="{c["cx"]}" cy="{c["cy"]}" r="{c["r"]}" '
                    f'fill="{c["color"]}" fill-opacity="{c.get("opacity",0.55)}"/>')
    for c in cfg["circles"]:
        if c.get("label"):
            lx = c.get("label_x", c["cx"])
            ly = c.get("label_y", c["cy"])
            body.append(text.label(lx, ly, c["label"], c.get("label_size", 18),
                        color=c.get("label_color", "#fff"), weight="700"))
    for ov in cfg.get("overlaps", []):
        body.append(text.label(ov["x"], ov["y"], ov["label"], ov.get("size", 14),
                    color=ov.get("color", "#333"), weight="600"))

    doc = canvas.svg(cfg["width"], cfg["height"], "", "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
