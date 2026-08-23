"""Reusable geometry primitives. No diagram-specific logic here.

Compute geometry, never eyeball it. Every radial/arc/segmented shape in this
package is produced by trigonometry, not hand-tuned path strings — see
../CLAUDE.md ("Critical Rule: Compute Geometry, Never Eyeball It") for why
this module exists: hand-authored arcs are exactly where SVG reconstructions
break (mismatched angles, flat trapezoids standing in for rounded segments,
labels that drift off their arc).
"""
import math


def polar(cx, cy, r, deg):
    """Point on a circle. 0deg = top, clockwise (matches clock-face intuition,
    and matches how reference screenshots are almost always annotated)."""
    a = math.radians(deg - 90)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


def arc_segment(cx, cy, r_in, r_out, start, end, corner=0):
    """Donut/pie/gauge/sunburst segment. corner>0 rounds all four corners.

    r_in=0 degenerates to a pie slice (no inner arc). This is the single
    most-reused primitive in the package — donut, pie, gauge, and sunburst
    recipes all call this.
    """
    def f(p):
        return f"{p[0]:.2f} {p[1]:.2f}"

    if r_in <= 0:
        # Pie slice: no inner arc, both radial edges meet at the center.
        # Handled before any r_in-based division so corner-rounding math
        # below never divides by zero.
        large = 1 if (end - start) > 180 else 0
        pO1 = polar(cx, cy, r_out, start)
        pO2 = polar(cx, cy, r_out, end)
        return (
            f"M {cx:.2f} {cy:.2f} L {f(pO1)} "
            f"A {r_out} {r_out} 0 {large} 1 {f(pO2)} Z"
        )

    def off(r):
        return math.degrees(corner / r) if (r and corner) else 0

    so, eo = start + off(r_out), end - off(r_out)
    si, ei = start + off(r_in), end - off(r_in)

    pO1 = polar(cx, cy, r_out, so)
    pO2 = polar(cx, cy, r_out, eo)
    pI2 = polar(cx, cy, r_in, ei)
    pI1 = polar(cx, cy, r_in, si)

    cOs = polar(cx, cy, r_out - corner, start)
    cOe = polar(cx, cy, r_out - corner, end)
    cIe = polar(cx, cy, r_in + corner, end)
    cIs = polar(cx, cy, r_in + corner, start)

    qOs = polar(cx, cy, r_out, start)
    qOe = polar(cx, cy, r_out, end)
    qIe = polar(cx, cy, r_in, end)
    qIs = polar(cx, cy, r_in, start)

    large = 1 if (eo - so) > 180 else 0

    return (
        f"M {f(cOs)} "
        f"Q {f(qOs)} {f(pO1)} "
        f"A {r_out} {r_out} 0 {large} 1 {f(pO2)} "
        f"Q {f(qOe)} {f(cOe)} "
        f"L {f(cIe)} "
        f"Q {f(qIe)} {f(pI2)} "
        f"A {r_in} {r_in} 0 {large} 0 {f(pI1)} "
        f"Q {f(qIs)} {f(cIs)} Z"
    )


def rounded_rect(x, y, w, h, r):
    """Bars, cards, nodes, buttons."""
    r = min(r, w / 2, h / 2)
    return (
        f"M {x+r:.2f} {y:.2f} h {w-2*r:.2f} "
        f"a {r} {r} 0 0 1 {r} {r} v {h-2*r:.2f} "
        f"a {r} {r} 0 0 1 {-r} {r} h {-(w-2*r):.2f} "
        f"a {r} {r} 0 0 1 {-r} {-r} v {-(h-2*r):.2f} "
        f"a {r} {r} 0 0 1 {r} {-r} Z"
    )


def smooth_line(points):
    """Catmull-Rom -> cubic Bezier through points. Line charts, flows."""
    if len(points) < 2:
        return ""
    d = f"M {points[0][0]:.2f} {points[0][1]:.2f} "
    p = points
    for i in range(len(p) - 1):
        p0 = p[i - 1] if i > 0 else p[i]
        p1, p2 = p[i], p[i + 1]
        p3 = p[i + 2] if i + 2 < len(p) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C {c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {p2[0]:.2f} {p2[1]:.2f} "
    return d


def elbow_connector(x1, y1, x2, y2, radius=8):
    """Rounded orthogonal (90-degree) connector. Flowcharts, org charts,
    hub-and-spoke systems where the reference uses right-angle routing
    instead of curved beziers — this is the primitive that fixes the
    'connectors should be 90 degrees, not smooth curves' class of feedback."""
    mx = (x1 + x2) / 2
    return (
        f"M {x1:.2f} {y1:.2f} H {mx-radius:.2f} "
        f"Q {mx:.2f} {y1:.2f} {mx:.2f} {y1 + (radius if y2>y1 else -radius):.2f} "
        f"V {y2 - (radius if y2>y1 else -radius):.2f} "
        f"Q {mx:.2f} {y2:.2f} {mx+radius:.2f} {y2:.2f} H {x2:.2f}"
    )


def elbow_bus(x1, y1, points_x, y_bus, cx_final, y2, radius=8):
    """Multiple sources converging on one vertical bus then dropping into a
    single target — the exact shape needed when several boxes drop straight
    down, join a horizontal bus, then one arrow continues into a card below.
    Returns a list of path strings: one drop-line per source + one bus line
    + one final connector into the target."""
    paths = []
    for x in points_x:
        paths.append(f"M {x:.2f} {y1:.2f} L {x:.2f} {y_bus:.2f}")
    paths.append(f"M {min(points_x):.2f} {y_bus:.2f} L {max(points_x):.2f} {y_bus:.2f}")
    paths.append(f"M {cx_final:.2f} {y_bus:.2f} L {cx_final:.2f} {y2:.2f}")
    return paths


def text_arc(cx, cy, r, start, end, reverse=False):
    """Path for <textPath> curved labels.

    <textPath> orients glyphs with "up" to the left of the direction of
    travel. Traversing top-half arcs with increasing angle (this module's
    clockwise convention) puts "up" pointing outward — correct. On the
    bottom half that same direction of travel puts "up" pointing inward,
    so the label renders upside-down (caught by actually rendering a
    bottom-half donut segment, not by reading the arc math — the sweep
    flag alone doesn't reveal it). reverse=True traces the identical arc
    end-to-start with the sweep flag inverted, keeping the same visual arc
    but flipping the direction of travel so bottom-half labels stay
    upright. Callers should pass reverse=True whenever the label's
    midpoint angle falls in (90, 270)."""
    p1, p2 = polar(cx, cy, r, start), polar(cx, cy, r, end)
    large = 1 if (end - start) > 180 else 0
    sweep = 1
    if reverse:
        p1, p2 = p2, p1
        sweep = 0
    return f"M {p1[0]:.2f} {p1[1]:.2f} A {r} {r} 0 {large} {sweep} {p2[0]:.2f} {p2[1]:.2f}"


def segment_midangle(start, end):
    return (start + end) / 2


def arc_length(r, span_deg):
    """Chord-ignoring arc length in px — used to check whether a label actually fits
    a curved path before committing to textPath (see text.curve_legible)."""
    return abs(span_deg) * math.pi / 180 * r


def hexagon(cx, cy, size):
    """Flat-top/bottom, pointed-left/right hexagon (the common
    architecture-diagram/PPT hexagon glyph — vertices at 0/60/120/180/240/300
    degrees from center puts the sharp points on the left/right and a flat
    edge on top/bottom). size = center-to-vertex radius. Returns an SVG
    polygon `points` attribute value, not a path."""
    pts = []
    for i in range(6):
        a = math.radians(60 * i)
        pts.append(f"{cx + size * math.cos(a):.2f},{cy - size * math.sin(a):.2f}")
    return " ".join(pts)


def label_rotation(mid_angle):
    """Rotation (degrees) for a straight label at a radial angle so it
    reads tangent to the circle and never upside-down.

    Derivation: the tangent line at angle theta (this module's 0deg=top,
    clockwise convention, verified against SVG's y-down rotate()) is the
    horizontal line rotated by theta degrees — so raw rotation = mid_angle.
    Normalize into (-90, 90] by subtracting/adding 180 so the bottom half
    of the ring doesn't render upside-down (a label rotated exactly 180
    from horizontal is mirrored, not just flipped — readers can't parse
    it). Verify empirically before trusting by hand: label_rotation(0)
    must be 0 (top, unrotated), label_rotation(90) must be 90 (right side,
    vertical), label_rotation(180) must be 0 (bottom, flipped back to
    horizontal, not left at 180).
    """
    r = mid_angle % 360
    if r > 180:
        r -= 360
    while r > 90:
        r -= 180
    while r < -90:
        r += 180
    return r
