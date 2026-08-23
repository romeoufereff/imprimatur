"""Text placement: straight, multi-line, curved (textPath).

font_family defaults to the active design system's font stack (see presets.FONT_FAMILY)
so labels match the surrounding HTML slide without the caller having to
repeat the family string in every config.
"""
from . import presets


def label(x, y, text, size, color="#fff", weight="700",
          anchor="middle", baseline="middle", family=None,
          rotate=None, letter_spacing=None):
    family = family or presets.FONT_FAMILY
    tr = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    ls = f' letter-spacing="{letter_spacing}"' if letter_spacing else ""
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{color}" '
        f'font-weight="{weight}" font-family="{family}" '
        f'text-anchor="{anchor}" dominant-baseline="{baseline}"{ls}{tr}>'
        f"{_esc(text)}</text>"
    )


def multiline(x, y, lines, size, line_height=None, color="#fff",
              weight="700", anchor="middle", family=None, rotate=None):
    family = family or presets.FONT_FAMILY
    lh = line_height or size * 1.15
    start = y - (len(lines) - 1) * lh / 2
    spans = "".join(
        f'<tspan x="{x:.2f}" y="{start + i*lh:.2f}">{_esc(t)}</tspan>'
        for i, t in enumerate(lines)
    )
    tr = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    return (
        f'<text font-size="{size}" fill="{color}" font-weight="{weight}" '
        f'font-family="{family}" text-anchor="{anchor}" '
        f'dominant-baseline="middle"{tr}>{spans}</text>'
    )


def curved(path_id, path_d, text, size, color="#fff", weight="700",
           family=None, offset="50%", anchor="middle"):
    """Requires the path added to <defs>. Returns (defs_fragment, body).

    Use for labels that follow a segment's arc (donut/pie/gauge/cycle wedge
    labels curving with the ring) — never fake curved text by rotating a
    straight label; it reads as tilted, not curved, past ~15 degrees of arc.
    """
    family = family or presets.FONT_FAMILY
    defs = f'<path id="{path_id}" d="{path_d}" fill="none"/>'
    body = (
        f'<text font-size="{size}" fill="{color}" font-weight="{weight}" '
        f'font-family="{family}">'
        f'<textPath href="#{path_id}" startOffset="{offset}" '
        f'text-anchor="{anchor}">{_esc(text)}</textPath></text>'
    )
    return defs, body


def curve_legible(r, span_deg, text_str, size):
    """Would `text_str` at font-size `size` actually fit along an arc of radius r
    spanning span_deg without the glyphs overlapping/compressing? Curved text has
    less tolerance than straight kerning suggests — glyphs on a tight radius fan out
    from a single baseline circle, so budget ~20% more advance width than flat text.
    This is the check that should gate every `curve:true` config value; a config
    author (or an agent defaulting to curve for a diagram with no reference to
    verify against) should not get warped, overlapping letters just because they
    asked for curved text on an arc too short to hold it."""
    from . import geometry as g
    needed = len(str(text_str)) * size * 0.62 * 1.2
    return g.arc_length(r, span_deg) >= needed


def smart_label(cx, cy, r, start, end, text_str, size, color="#fff", weight="700",
                 path_id="lbl", family=None, force=None):
    """Curved where the arc can hold it legibly, straight tangent-rotated otherwise —
    always returns (defs, body) so callers can treat both cases uniformly.

    This is the fix for the exact failure this skill's own origin story hit by hand
    (see references/embedding-example.md): round 1 tried curved/rotated labels that
    didn't fit and read as warped or overlapping; the working fix was a straight
    label rotated to the arc's tangent (geometry.label_rotation). Use this instead of
    hand-picking curve vs straight per label — `force=True`/`force=False` still lets
    a reference-matched reconstruction override the legibility check when the
    screenshot genuinely shows true curved text on a tight arc (rare, but MEASURE
    should have already confirmed it, not guessed it).
    """
    from . import geometry as g
    mid = (start + end) / 2
    use_curve = force if force is not None else curve_legible(r, end - start, text_str, size)
    if use_curve:
        bottom_half = 90 < (mid % 360) < 270
        pd = g.text_arc(cx, cy, r, start + 2, end - 2, reverse=bottom_half)
        return curved(path_id, pd, text_str, size, color=color, weight=weight, family=family)
    lx, ly = g.polar(cx, cy, r, mid)
    return "", label(lx, ly, text_str, size, color=color, weight=weight,
                      family=family, rotate=g.label_rotation(mid))


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))
