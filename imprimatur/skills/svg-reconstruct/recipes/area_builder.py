"""Builder for area charts (reuses line-chart logic with forced area fill)."""
from svgkit import geometry as g, gradients as grad, text, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    p = cfg["plot"]
    ymin, ymax = cfg["y_axis"]["min"], cfg["y_axis"]["max"]
    ticks = cfg["y_axis"].get("ticks", 5)
    xlabels = cfg["x_axis"]["labels"]
    defs, body = [], []

    def y_of(v): return p["y"] + p["h"] * (1 - (v-ymin)/(ymax-ymin))
    def x_of(i): return p["x"] + p["w"] * i / max(len(xlabels)-1, 1)

    for i in range(ticks+1):
        val = ymin + (ymax-ymin)*i/ticks
        gy = y_of(val)
        body.append(f'<line x1="{p["x"]}" y1="{gy:.1f}" x2="{p["x"]+p["w"]}" '
                    f'y2="{gy:.1f}" stroke="{presets.RULE}"/>')
        body.append(text.label(p["x"]-12, gy, f"{val:g}", 12, color="#888",
                    weight="400", anchor="end"))

    for si, s in enumerate(cfg["series"]):
        pts = [(x_of(i), y_of(v)) for i, v in enumerate(s["points"])]
        pd = g.smooth_line(pts) if cfg.get("smooth", True) else \
             "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        gid = f"area{si}"
        defs.append(grad.linear(gid, 90, [["0%", s["color"], 0.55],
                                          ["100%", s["color"], 0.05]]))
        area = pd + f" L {pts[-1][0]:.1f} {p['y']+p['h']} " \
                    f"L {pts[0][0]:.1f} {p['y']+p['h']} Z"
        body.append(f'<path d="{area}" fill="url(#{gid})"/>')
        body.append(f'<path d="{pd}" fill="none" stroke="{s["color"]}" '
                    f'stroke-width="{s.get("width",3)}"/>')

    for i, lbl in enumerate(xlabels):
        body.append(text.label(x_of(i), p["y"]+p["h"]+22, lbl, 12,
                    color="#888", weight="400"))

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
