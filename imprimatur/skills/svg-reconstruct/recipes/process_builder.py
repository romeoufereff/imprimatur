"""Builder for chevron/arrow process charts."""
from svgkit import gradients as grad, text, icons, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    x = cfg["start_x"]; y = cfg["y"]
    w, h = cfg["step_w"], cfg["step_h"]
    notch = cfg.get("notch", 24)
    gap = cfg.get("gap", 6)
    defs, body = [], []

    for i, s in enumerate(cfg["steps"]):
        gid = f"proc{i}"
        n = len(cfg["steps"])
        if "stops" in s or "color" not in s:
            stops = s.get("stops") or presets.sequential_stops(i, n)
            defs.append(grad.linear(gid, 0, stops)); fill = f"url(#{gid})"
        else:
            fill = s["color"]  # explicit flat choice, respected as-is
        pts = (f"{x},{y} {x+w-notch},{y} {x+w},{y+h/2} {x+w-notch},{y+h} "
               f"{x},{y+h} {x+notch if i>0 else x},{y+h/2}")
        body.append(f'<polygon points="{pts}" fill="{fill}"/>')
        cx = x + w/2
        if s.get("icon"):
            body.append(icons.place(s["icon"], cx, y+h/2-14, 26, color="#fff"))
        body.append(text.label(cx, y+h/2+16, s["label"], 15, color="#fff", weight="700"))
        x += w - notch + gap

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
