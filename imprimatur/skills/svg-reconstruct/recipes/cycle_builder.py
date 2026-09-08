"""Builder for circular cycle diagrams."""
from svgkit import geometry as g, gradients as grad, text, icons, canvas, schema, presets

ARROW = ('<marker id="cyc-arrow" markerWidth="12" markerHeight="12" refX="6" '
         f'refY="3" orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="{presets.PRIMARY}"/></marker>')


def build(config_path, out_svg_path=None):
    """Circular arrangement of steps with curved arrows between them."""
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    cx, cy = cfg["center"]
    R = cfg["radius"]; node_r = cfg.get("node_radius", 55)
    steps = cfg["steps"]; n = len(steps)
    defs, body = [ARROW], []

    positions = []
    for i in range(n):
        ang = 360 * i / n + cfg.get("rotation", 0)
        positions.append((*g.polar(cx, cy, R, ang), ang))

    for i in range(n):
        a0 = positions[i][2]
        a1 = positions[(i+1) % n][2]
        if a1 < a0:
            a1 += 360
        pd = g.text_arc(cx, cy, R, a0 + 20, a1 - 20)
        body.append(f'<path d="{pd}" fill="none" stroke="{presets.PRIMARY}" '
                    f'stroke-width="3" marker-end="url(#cyc-arrow)" opacity="0.5"/>')

    for i, s in enumerate(steps):
        px, py, ang = positions[i]
        gid = f"cyc{i}"
        if "stops" in s or "color" not in s:
            stops = s.get("stops") or presets.sequential_stops(i, n)
            defs.append(grad.linear(gid, 135, stops)); fill = f"url(#{gid})"
        else:
            fill = s["color"]  # explicit flat choice, respected as-is
        body.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{node_r}" fill="{fill}"/>')
        if s.get("icon"):
            body.append(icons.place(s["icon"], px, py-10, 28, color="#fff"))
        body.append(text.label(px, py+22, s["label"], 13, color="#fff", weight="700"))

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
