"""Builder for gauge / radial progress diagrams."""
from svgkit import geometry as g, gradients as grad, text, canvas, schema, presets


def build(config_path, out_svg_path=None):
    """Semi/full gauge. config: center, r_in, r_out, min, max, value, arc angles."""
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    cx, cy = cfg["center"]
    ri, ro = cfg["r_inner"], cfg["r_outer"]
    a0 = cfg.get("start_angle", -120)
    a1 = cfg.get("end_angle", 120)
    vmin, vmax, val = cfg["min"], cfg["max"], cfg["value"]
    defs, body = [], []

    body.append(f'<path d="{g.arc_segment(cx, cy, ri, ro, a0, a1, corner=(ro-ri)/2)}" '
                f'fill="{cfg.get("track_color",presets.RULE)}"/>')
    va = a0 + (a1 - a0) * (val - vmin) / (vmax - vmin)
    if "stops" in cfg:
        defs.append(grad.linear("gaugev", 0, cfg["stops"])); fill = "url(#gaugev)"
    elif "value_color" in cfg:
        fill = cfg["value_color"]  # explicit flat choice, respected as-is
    else:
        # Default: a real light/dark gradient on the fill, not a flat brand color —
        # a gauge arc is one continuous shape, so even one hue reads with more
        # depth when it isn't perfectly flat. See gradients.auto.
        defs.append(grad.auto("gaugev", presets.PRIMARY)); fill = "url(#gaugev)"
    body.append(f'<path d="{g.arc_segment(cx, cy, ri, ro, a0, va, corner=(ro-ri)/2)}" '
                f'fill="{fill}"/>')
    body.append(text.label(cx, cy, cfg.get("display", f"{val:g}"),
                cfg.get("value_size", 48), color="#333", weight="800"))
    if cfg.get("subtitle"):
        body.append(text.label(cx, cy+40, cfg["subtitle"], 15, color="#777", weight="500"))

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", "#ffffff"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
