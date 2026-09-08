"""Builder for swimlane roadmaps."""
from svgkit import geometry as g, gradients as grad, text, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    ox, oy = cfg["origin"]
    lane_h = cfg["lane_height"]; col_w = cfg["col_width"]
    label_w = cfg.get("lane_label_width", 140)
    lanes = cfg["lanes"]; cols = cfg["columns"]
    corner = cfg.get("corner", 8)
    defs, body = [], []

    for ci, c in enumerate(cols):
        x = ox + label_w + ci*col_w
        body.append(text.label(x+col_w/2, oy-14, c, 14, color="#555", weight="700"))

    for li, lane in enumerate(lanes):
        y = oy + li*lane_h
        body.append(f'<rect x="{ox}" y="{y}" width="{label_w+len(cols)*col_w}" '
                    f'height="{lane_h}" fill="{presets.SURFACE if li%2==0 else "#fff"}"/>')
        body.append(text.label(ox+12, y+lane_h/2, lane, 13, color="#333",
                    weight="700", anchor="start"))

    for it in cfg["items"]:
        li = lanes.index(it["lane"]); ci = it["col"]; span = it.get("span", 1)
        x = ox + label_w + ci*col_w + 6
        y = oy + li*lane_h + 10
        w_ = span*col_w - 12; h = lane_h - 20
        gid = f"rm{li}-{ci}"
        if "stops" in it:
            defs.append(grad.linear(gid, 0, it["stops"])); fill = f"url(#{gid})"
        elif "color" in it:
            fill = it["color"]  # explicit flat choice, respected as-is
        else:
            # A roadmap bar is one initiative in a lane, not a category wheel —
            # default to depth only, matching flowchart/org_chart's rule.
            defs.append(grad.auto(gid, presets.PRIMARY)); fill = f"url(#{gid})"
        body.append(f'<path d="{g.rounded_rect(x, y, w_, h, corner)}" fill="{fill}"/>')
        body.append(text.label(x+w_/2, y+h/2, it["label"], 13, color="#fff", weight="600"))

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
