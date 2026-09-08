"""Builder for funnel charts."""
from svgkit import gradients as grad, text, icons, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    cx = cfg["center_x"]
    y = cfg["top"]
    bh, gap = cfg["band_height"], cfg.get("gap", 8)
    wmax, wmin = cfg["max_width"], cfg["min_width"]
    stages = cfg["stages"]
    vmax = max(s["value"] for s in stages)
    defs, body = [], []

    for i, s in enumerate(stages):
        frac = s["value"] / vmax
        w_top = wmin + (wmax - wmin) * frac
        nxt = stages[i+1]["value"]/vmax if i+1 < len(stages) else frac*0.85
        w_bot = wmin + (wmax - wmin) * nxt
        x_tl, x_tr = cx - w_top/2, cx + w_top/2
        x_bl, x_br = cx - w_bot/2, cx + w_bot/2
        gid = f"fun{i}"
        if "stops" in s or "color" not in s:
            stops = s.get("stops") or presets.sequential_stops(i, len(stages))
            defs.append(grad.linear(gid, 90, stops)); fill = f"url(#{gid})"
        else:
            fill = s["color"]  # explicit flat choice, respected as-is
        body.append(f'<polygon points="{x_tl:.1f},{y:.1f} {x_tr:.1f},{y:.1f} '
                    f'{x_br:.1f},{y+bh:.1f} {x_bl:.1f},{y+bh:.1f}" fill="{fill}"/>')
        tx = cx
        if s.get("icon"):
            body.append(icons.place(s["icon"], cx - w_top/2 + 30, y+bh/2, 24, color="#fff"))
        body.append(text.label(tx, y+bh/2-8, s["label"], 16, color="#fff", weight="700"))
        body.append(text.label(tx, y+bh/2+14, f'{s["value"]:,}', 13,
                    color="#fff", weight="500"))
        y += bh + gap

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
