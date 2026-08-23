"""Builder for hub-and-spoke diagrams."""
from svgkit import geometry as g, gradients as grad, text, icons, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    cx, cy = cfg["center"]
    R = cfg["spoke_radius"]
    hr = cfg["hub"].get("radius", 80)
    sr = cfg.get("spoke_node_radius", 55)
    spokes = cfg["spokes"]; n = len(spokes)
    defs, body = [], []

    for i in range(n):
        ang = 360*i/n + cfg.get("rotation", 0)
        px, py = g.polar(cx, cy, R, ang)
        body.append(f'<line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" '
                    f'stroke="{cfg.get("line_color",presets.RULE)}" stroke-width="3"/>')

    hub_grad = cfg["hub"].get("gradient") or [presets.ACCENT, presets._shade(presets.ACCENT, -0.25)]
    defs.append(grad.radial("hubg", [["0%", hub_grad[0], 1], ["100%", hub_grad[1], 1]],
                            fx="35%", fy="35%"))
    defs.append(grad.drop_shadow("hubSpokeShadow", dy=6, blur=10, opacity=0.18))
    body.append(f'<circle cx="{cx}" cy="{cy}" r="{hr}" fill="url(#hubg)" '
                f'filter="url(#hubSpokeShadow)"/>')
    body.append(text.label(cx, cy, cfg["hub"]["label"], cfg["hub"].get("size", 22),
                color="#fff", weight="800"))

    for i, s in enumerate(spokes):
        ang = 360*i/n + cfg.get("rotation", 0)
        px, py = g.polar(cx, cy, R, ang)
        gid = f"sp{i}"
        if "stops" in s or "color" not in s:
            # Spokes denote distinct categories around a hub, same as donut
            # wedges — default to hue-varied stops, not one repeated flat color.
            stops = s.get("stops") or presets.sequential_stops(i, n)
            defs.append(grad.linear(gid, 135, stops)); fill = f"url(#{gid})"
        else:
            fill = s["color"]  # explicit flat choice, respected as-is
        body.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{sr}" fill="{fill}"/>')
        if s.get("icon"):
            body.append(icons.place(s["icon"], px, py-12, 26, color="#fff"))
        body.append(text.label(px, py+20, s["label"], 12, color="#fff", weight="700"))

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
