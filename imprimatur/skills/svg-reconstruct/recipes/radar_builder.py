"""Builder for radar / spider charts."""
from svgkit import geometry as g, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    cx, cy = cfg["center"]; R = cfg["radius"]
    axes = cfg["axes"]; n = len(axes)
    rings = cfg.get("rings", 5); vmax = cfg.get("max", 100)
    body = []

    for r in range(1, rings+1):
        rr = R * r / rings
        pts = " ".join(f"{g.polar(cx,cy,rr,360*i/n)[0]:.1f},"
                       f"{g.polar(cx,cy,rr,360*i/n)[1]:.1f}" for i in range(n))
        body.append(f'<polygon points="{pts}" fill="none" stroke="{presets.RULE}"/>')

    from svgkit import text
    for i, ax in enumerate(axes):
        ex, ey = g.polar(cx, cy, R, 360*i/n)
        body.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" '
                    f'stroke="{presets.RULE}"/>')
        lx, ly = g.polar(cx, cy, R+24, 360*i/n)
        body.append(text.label(lx, ly, ax, 12, color="#555", weight="600"))

    for s in cfg["series"]:
        pts = []
        for i, v in enumerate(s["values"]):
            rr = R * v / vmax
            px, py = g.polar(cx, cy, rr, 360*i/n)
            pts.append(f"{px:.1f},{py:.1f}")
        body.append(f'<polygon points="{" ".join(pts)}" '
                    f'fill="{s["color"]}" fill-opacity="0.25" '
                    f'stroke="{s["color"]}" stroke-width="2.5"/>')

    doc = canvas.svg(cfg["width"], cfg["height"], "", "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
