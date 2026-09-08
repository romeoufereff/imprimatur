"""Builder for stacked bar charts."""
from svgkit import text, canvas, schema


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    p = cfg["plot"]
    cats = cfg["categories"]; segs = cfg["segments"]
    totals = [sum(s["values"][i] for s in segs) for i in range(len(cats))]
    ymax = cfg.get("max") or max(totals) * 1.1
    body = []

    def y_of(v): return p["y"] + p["h"] * (1 - v/ymax)
    slot = p["w"] / len(cats); bw = slot * (1 - cfg.get("gap_ratio", 0.4))

    for ci, cat in enumerate(cats):
        bx = p["x"] + slot*ci + (slot-bw)/2
        stack = 0
        for s in segs:
            v = s["values"][ci]
            top = y_of(stack + v); h = y_of(stack) - top
            body.append(f'<rect x="{bx:.1f}" y="{top:.1f}" width="{bw:.1f}" '
                        f'height="{h:.1f}" fill="{s["color"]}"/>')
            stack += v
        body.append(text.label(bx+bw/2, p["y"]+p["h"]+22, cat, 13,
                    color="#333", weight="600"))

    lx = p["x"]
    for s in segs:
        body.append(f'<rect x="{lx}" y="{p["y"]-30}" width="14" height="14" '
                    f'rx="3" fill="{s["color"]}"/>')
        body.append(text.label(lx+20, p["y"]-23, s["name"], 12, color="#333",
                    weight="500", anchor="start"))
        lx += 34 + len(s["name"])*7

    body.append(f'<line x1="{p["x"]}" y1="{p["y"]+p["h"]}" x2="{p["x"]+p["w"]}" '
                f'y2="{p["y"]+p["h"]}" stroke="#333"/>')

    doc = canvas.svg(cfg["width"], cfg["height"], "", "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
