"""Builder for line charts (image-reconstruction use case — see line.md)."""
from svgkit import geometry as g, gradients as grad, text, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    p = cfg["plot"]
    ymin, ymax = cfg["y_axis"]["min"], cfg["y_axis"]["max"]
    ticks = cfg["y_axis"].get("ticks", 5)
    xlabels = cfg["x_axis"]["labels"]
    smooth = cfg.get("smooth", True)
    defs, body = [], []

    def y_of(v): return p["y"] + p["h"] * (1 - (v - ymin) / (ymax - ymin))
    def x_of(i): return p["x"] + p["w"] * i / max(len(xlabels) - 1, 1)

    if cfg.get("grid", True):
        for i in range(ticks + 1):
            val = ymin + (ymax - ymin) * i / ticks
            gy = y_of(val)
            body.append(f'<line x1="{p["x"]}" y1="{gy:.1f}" x2="{p["x"]+p["w"]}" '
                        f'y2="{gy:.1f}" stroke="{presets.RULE}"/>')
            body.append(text.label(p["x"]-12, gy, f"{val:g}", 13, color="#666",
                        weight="400", anchor="end"))

    for i, lbl in enumerate(xlabels):
        body.append(text.label(x_of(i), p["y"]+p["h"]+22, lbl, 13,
                    color="#666", weight="400"))

    for si, s in enumerate(cfg["series"]):
        pts = [(x_of(i), y_of(v)) for i, v in enumerate(s["points"])]
        path_d = g.smooth_line(pts) if smooth else \
                 "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)

        if s.get("area"):
            gid = f"area{si}"
            defs.append(grad.linear(gid, 90, [
                ["0%", s["color"], 0.35], ["100%", s["color"], 0.02]]))
            area = path_d + f" L {pts[-1][0]:.2f} {p['y']+p['h']} " \
                            f"L {pts[0][0]:.2f} {p['y']+p['h']} Z"
            body.append(f'<path d="{area}" fill="url(#{gid})"/>')

        body.append(f'<path d="{path_d}" fill="none" stroke="{s["color"]}" '
                    f'stroke-width="{s.get("width",3)}" stroke-linecap="round" '
                    f'stroke-linejoin="round"/>')

        if s.get("dots"):
            for x, y in pts:
                body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.5" '
                            f'fill="#fff" stroke="{s["color"]}" stroke-width="2.5"/>')

    body.append(f'<line x1="{p["x"]}" y1="{p["y"]+p["h"]}" x2="{p["x"]+p["w"]}" '
                f'y2="{p["y"]+p["h"]}" stroke="#333"/>')
    body.append(f'<line x1="{p["x"]}" y1="{p["y"]}" x2="{p["x"]}" '
                f'y2="{p["y"]+p["h"]}" stroke="#333"/>')

    if len(cfg["series"]) > 1:
        lx = p["x"] + 10
        for s in cfg["series"]:
            body.append(f'<rect x="{lx}" y="{p["y"]-28}" width="14" height="14" '
                        f'rx="3" fill="{s["color"]}"/>')
            body.append(text.label(lx+20, p["y"]-21, s["name"], 13, color="#333",
                        weight="600", anchor="start"))
            lx += 30 + len(s["name"]) * 8

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
