"""Builder for pyramid charts."""
from svgkit import gradients as grad, text, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    cx = cfg["center_x"]
    y = cfg["top"]
    bh, gap = cfg["band_height"], cfg.get("gap", 6)
    apex_w = cfg.get("apex_width", 40)
    base_w = cfg["base_width"]
    levels = cfg["levels"]  # top -> bottom
    n = len(levels)
    defs, body = [], []

    for i, lvl in enumerate(levels):
        w_top = apex_w + (base_w - apex_w) * (i / n)
        w_bot = apex_w + (base_w - apex_w) * ((i+1) / n)
        x_tl, x_tr = cx - w_top/2, cx + w_top/2
        x_bl, x_br = cx - w_bot/2, cx + w_bot/2
        gid = f"pyr{i}"
        if "stops" in lvl or "color" not in lvl:
            stops = lvl.get("stops") or presets.sequential_stops(i, n)
            defs.append(grad.linear(gid, 135, stops)); fill = f"url(#{gid})"
        else:
            fill = lvl["color"]  # explicit flat choice, respected as-is
        body.append(f'<polygon points="{x_tl:.1f},{y:.1f} {x_tr:.1f},{y:.1f} '
                    f'{x_br:.1f},{y+bh:.1f} {x_bl:.1f},{y+bh:.1f}" fill="{fill}"/>')
        body.append(text.label(cx, y+bh/2, lvl["label"], 15, color="#fff", weight="700"))
        y += bh + gap

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
