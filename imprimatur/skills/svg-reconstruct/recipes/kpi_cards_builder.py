"""Builder for KPI card grids."""
from svgkit import geometry as g, gradients as grad, text, icons, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)
    cols = cfg["grid"]["cols"]; gap = cfg["grid"].get("gap", 24)
    cw, ch = cfg["card"]["w"], cfg["card"]["h"]
    corner = cfg["card"].get("corner", 16)
    ox, oy = cfg.get("origin", [40, 40])
    defs, body = [grad.drop_shadow("cardshadow")], []

    for i, c in enumerate(cfg["cards"]):
        r, col = divmod(i, cols)
        x = ox + col*(cw+gap); y = oy + r*(ch+gap)
        gid = f"kpi{i}"
        if "stops" in c:
            defs.append(grad.linear(gid, 135, c["stops"])); fill = f"url(#{gid})"
        else:
            fill = c.get("color", "#ffffff")
        body.append(f'<path d="{g.rounded_rect(x, y, cw, ch, corner)}" '
                    f'fill="{fill}" filter="url(#cardshadow)"/>')
        tcol = c.get("text_color", "#fff" if "stops" in c else "#333")
        if c.get("icon"):
            body.append(icons.place(c["icon"], x+34, y+34, 28, color=tcol))
        body.append(text.label(x+24, y+ch*0.5, c["value"], 34, color=tcol,
                    weight="800", anchor="start"))
        body.append(text.label(x+24, y+ch*0.72, c["label"], 14,
                    color=tcol, weight="500", anchor="start"))
        if c.get("delta"):
            dc = presets.POSITIVE if str(c["delta"]).startswith("+") else presets.NEGATIVE
            body.append(text.label(x+cw-24, y+34, c["delta"], 14, color=dc,
                        weight="700", anchor="end"))

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background", presets.SURFACE))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
