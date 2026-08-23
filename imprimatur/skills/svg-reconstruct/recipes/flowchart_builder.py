"""Builder for flowchart / node-edge diagrams."""
from svgkit import geometry as g, gradients as grad, text, icons, canvas, schema, presets

ARROW = ('<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" '
         'refY="3" orient="auto" markerUnits="strokeWidth">'
         '<path d="M0,0 L8,3 L0,6 Z" fill="#555"/></marker>')


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    corner = cfg.get("corner", 10)
    nodes = {n["id"]: n for n in cfg["nodes"]}
    defs, body = [ARROW], []

    def anchor(n, side):
        cx, cy = n["x"] + n["w"]/2, n["y"] + n["h"]/2
        return {"r": (n["x"]+n["w"], cy), "l": (n["x"], cy),
                "t": (cx, n["y"]), "b": (cx, n["y"]+n["h"])}[side]

    for e in cfg["edges"]:
        a, b = nodes[e["from"]], nodes[e["to"]]
        x1, y1 = anchor(a, "r"); x2, y2 = anchor(b, "l")
        if e.get("style", "elbow") == "straight":
            d = f"M {x1} {y1} L {x2} {y2}"
        else:
            d = g.elbow_connector(x1, y1, x2, y2)
        marker = ' marker-end="url(#arrow)"' if e.get("arrow", True) else ""
        body.append(f'<path d="{d}" fill="none" stroke="#555" '
                    f'stroke-width="2"{marker}/>')
        if e.get("label"):
            body.append(text.label((x1+x2)/2, (y1+y2)/2-8, e["label"], 12,
                        color="#555", weight="500"))

    for i, n in enumerate(cfg["nodes"]):
        gid = f"node{i}"
        if "stops" in n:
            defs.append(grad.linear(gid, n.get("gradient_angle", 135), n["stops"]))
            fill = f"url(#{gid})"
        elif "color" in n:
            fill = n["color"]  # explicit flat choice, respected as-is
        else:
            # Flowchart boxes are conventionally one consistent hue (they denote
            # process steps, not distinct categories) — default to depth via
            # gradients.auto, not hue-cycling like donut/funnel/hub-spoke.
            defs.append(grad.auto(gid, presets.PRIMARY)); fill = f"url(#{gid})"
        shape = n.get("shape", "rounded")
        if shape == "diamond":
            cx, cy = n["x"]+n["w"]/2, n["y"]+n["h"]/2
            body.append(f'<polygon points="{cx},{n["y"]} {n["x"]+n["w"]},{cy} '
                        f'{cx},{n["y"]+n["h"]} {n["x"]},{cy}" fill="{fill}"/>')
        else:
            r = 0 if shape == "rect" else corner
            body.append(f'<path d="{g.rounded_rect(n["x"],n["y"],n["w"],n["h"],r)}" '
                        f'fill="{fill}"/>')
        tx = n["x"]+n["w"]/2
        if n.get("icon"):
            body.append(icons.place(n["icon"], n["x"]+24, n["y"]+n["h"]/2, 24,
                        color=n.get("text_color", "#fff")))
            tx += 14
        body.append(text.label(tx, n["y"]+n["h"]/2, n["label"], 15,
                    color=n.get("text_color", "#fff"), weight="600"))

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
