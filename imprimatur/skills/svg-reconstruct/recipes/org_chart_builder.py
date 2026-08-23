"""Builder for org charts."""
from svgkit import geometry as g, gradients as grad, text, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    corner = cfg.get("corner", 10)
    nodes = {n["id"]: n for n in cfg["nodes"]}
    defs, body = [], []

    for n in cfg["nodes"]:
        if n.get("parent"):
            p = nodes[n["parent"]]
            x1, y1 = p["x"]+p["w"]/2, p["y"]+p["h"]
            x2, y2 = n["x"]+n["w"]/2, n["y"]
            midy = (y1+y2)/2
            body.append(f'<path d="M {x1} {y1} V {midy} H {x2} V {y2}" '
                        f'fill="none" stroke="{presets.RULE}" stroke-width="2"/>')

    for i, n in enumerate(cfg["nodes"]):
        gid = f"org{i}"
        if "stops" in n:
            defs.append(grad.linear(gid, 135, n["stops"])); fill = f"url(#{gid})"
        elif "color" in n:
            fill = n["color"]  # explicit flat choice, respected as-is
        else:
            # Org boxes are conventionally one consistent hue per level/department,
            # not a rainbow — default to depth only, matching flowchart's rule.
            defs.append(grad.auto(gid, presets.PRIMARY)); fill = f"url(#{gid})"
        body.append(f'<path d="{g.rounded_rect(n["x"],n["y"],n["w"],n["h"],corner)}" '
                    f'fill="{fill}"/>')
        cx = n["x"]+n["w"]/2
        body.append(text.label(cx, n["y"]+n["h"]*0.4, n["label"], 15,
                    color=n.get("text_color","#fff"), weight="700"))
        if n.get("role"):
            body.append(text.label(cx, n["y"]+n["h"]*0.68, n["role"], 12,
                        color=n.get("text_color","#fff"), weight="400"))

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
