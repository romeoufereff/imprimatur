"""Builder for segmented donut / radial diagrams."""
from svgkit import geometry as g, gradients as grad, text, icons, canvas, schema, presets


def build(config_path, out_svg_path=None):
    cfg = schema.load_config(config_path)
    schema.validate(cfg)

    cx, cy = cfg["center"]
    r_in, r_out, corner = cfg["r_inner"], cfg["r_outer"], cfg.get("corner", 0)
    defs, body = [], []
    n = len(cfg["segments"])

    # --- hub ---
    hub = cfg["hub"]
    hub_stops = hub.get("gradient") or [presets.ACCENT, presets._shade(presets.ACCENT, -0.25)]
    defs.append(grad.radial(
        "hub", [["0%", hub_stops[0], 1], ["100%", hub_stops[1], 1]],
        fx="35%", fy="35%",
    ))
    defs.append(grad.drop_shadow("hubShadow", dy=6, blur=10, opacity=0.18))
    body.append(
        f'<circle cx="{cx}" cy="{cy}" r="{hub.get("radius", r_in - 30)}" '
        f'fill="url(#hub)" filter="url(#hubShadow)"/>'
    )
    body.append(text.label(
        cx, cy, hub["label"], hub.get("font_size", 60),
        color=hub.get("color", "#fff"),
    ))

    # --- segments ---
    for i, s in enumerate(cfg["segments"]):
        gid = f"seg{i}"
        # Default to a real per-segment gradient (varied hue + genuine light/dark
        # stops) instead of requiring the config to supply "stops" — see
        # presets.sequential_stops. A config can still hand-author "stops" for an
        # exact reference match; this only fills the gap when it doesn't.
        stops = s.get("stops") or presets.sequential_stops(i, n)
        defs.append(grad.linear(gid, s.get("gradient_angle", 135), stops))
        body.append(
            f'<path d="{g.arc_segment(cx, cy, r_in, r_out, s["start"], s["end"], corner)}" '
            f'fill="url(#{gid})"/>'
        )

        mid = g.segment_midangle(s["start"], s["end"])
        span = s["end"] - s["start"]

        lab = s.get("label")
        if lab:
            # "lines" supports a stacked headline+subtitle (e.g. "Knowledge" +
            # "of SMEs"), each its own radius/size. A single "text" is the common
            # one-line case. Legibility (text.smart_label) decides curved vs
            # straight per line — mixing the two within one stack reads broken, so
            # if ANY line can't hold a curve, the whole stack renders straight.
            lines = lab.get("lines") or [{
                "text": lab["text"],
                "radius": lab.get("radius", (r_in + r_out) / 2),
                "size": lab.get("size", 30),
            }]
            force = lab.get("curve")  # explicit override for a reference-verified case
            if force is None:
                all_curve_ok = all(
                    text.curve_legible(ln.get("radius", (r_in + r_out) / 2), span,
                                        ln["text"], ln.get("size", 30))
                    for ln in lines
                )
            else:
                all_curve_ok = force
            if len(lines) == 1:
                ln = lines[0]
                d, b = text.smart_label(cx, cy, ln.get("radius", (r_in + r_out) / 2),
                                         s["start"], s["end"], ln["text"], ln.get("size", 30),
                                         color=ln.get("color", lab.get("color", "#fff")),
                                         path_id=f"lp{i}_0", force=all_curve_ok if force is not None else None)
                defs.append(d); body.append(b)
            elif all_curve_ok:
                bottom_half = 90 < (mid % 360) < 270
                for j, ln in enumerate(lines):
                    r_txt = ln.get("radius", (r_in + r_out) / 2)
                    pd = g.text_arc(cx, cy, r_txt, s["start"] + 4, s["end"] - 4, reverse=bottom_half)
                    d, b = text.curved(f"lp{i}_{j}", pd, ln["text"], ln.get("size", 30),
                                       color=ln.get("color", lab.get("color", "#fff")))
                    defs.append(d); body.append(b)
            else:
                # Curve doesn't fit for at least one line — fall back to a
                # straight, tangent-rotated multiline stack (readable at any span).
                lx, ly = g.polar(cx, cy, lab.get("radius", (r_in + r_out) / 2 + 40), mid)
                rot = g.label_rotation(mid)
                texts = [ln["text"] for ln in lines]
                sizes = {ln["text"]: ln.get("size", 30) for ln in lines}
                body.append(text.multiline(lx, ly, texts, lines[0].get("size", 30),
                                           color=lab.get("color", "#fff"), rotate=rot))

        ic = s.get("icon")
        if ic:
            ix, iy = g.polar(cx, cy, ic.get("radius", (r_in + r_out) / 2 - 30), mid)
            body.append(icons.place(ic["name"], ix, iy, ic.get("size", 60),
                                    color=ic.get("color", "#fff")))

    doc = canvas.svg(cfg["width"], cfg["height"], "".join(defs), "".join(body),
                     bg=cfg.get("background"))
    out = out_svg_path or config_path.replace(".json", ".svg")
    open(out, "w").write(doc)
    return out
