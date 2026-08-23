"""The math, in isolation.

Geometry is the one part of this package where a wrong answer looks plausible —
an arc that is 3 degrees off still renders as an arc. These assert the conventions
the rest of the code relies on, including two bugs that actually shipped.
"""
import math

import pytest

from svgkit import geometry as g


# ── the angle convention every recipe assumes ────────────────────────────
def test_polar_zero_is_top():
    """0deg is the top of the circle, not the right — this matches how reference
    screenshots are annotated, and every recipe is written against it."""
    x, y = g.polar(100, 100, 50, 0)
    assert x == pytest.approx(100)
    assert y == pytest.approx(50)


def test_polar_is_clockwise():
    x, y = g.polar(100, 100, 50, 90)
    assert x == pytest.approx(150)   # 90deg lands on the right
    assert y == pytest.approx(100)


@pytest.mark.parametrize("deg,expect", [(0, (100, 50)), (90, (150, 100)),
                                        (180, (100, 150)), (270, (50, 100))])
def test_polar_quadrants(deg, expect):
    x, y = g.polar(100, 100, 50, deg)
    assert (round(x, 6), round(y, 6)) == pytest.approx(expect)


# ── regression: r_inner=0 used to divide by zero ─────────────────────────
def test_arc_segment_pie_slice_does_not_crash():
    """r_in=0 degenerates to a pie slice. This raised ZeroDivisionError once;
    donut, pie and gauge all route through here, so it took three recipes down."""
    d = g.arc_segment(100, 100, 0, 50, 0, 90)
    assert d and d.startswith("M")
    assert "nan" not in d.lower()


def test_arc_segment_donut_has_both_arcs():
    d = g.arc_segment(100, 100, 30, 50, 0, 90)
    assert d.count("A") == 2, "a donut segment needs an outer and an inner arc"


def test_arc_segment_full_circle_is_finite():
    d = g.arc_segment(100, 100, 20, 50, 0, 359.9)
    assert "nan" not in d.lower() and "inf" not in d.lower()


@pytest.mark.parametrize("corner", [0, 4, 12])
def test_arc_segment_corner_radius_stays_well_formed(corner):
    d = g.arc_segment(100, 100, 30, 60, 10, 80, corner=corner)
    assert d.startswith("M") and d.rstrip().endswith("Z")


# ── regression: label_rotation's convention is easy to get backwards ─────
@pytest.mark.parametrize("mid,expect", [(0, 0), (90, 90), (180, 0)])
def test_label_rotation_never_upside_down(mid, expect):
    """The three the docstring derives by hand, and warns are easy to get backwards.
    Asserting them is cheaper than re-deriving next time. 270deg is deliberately not
    here: the docstring does not derive it, and both -90 and +90 read legibly on the
    left of the ring — pinning one would encode a preference the code never stated."""
    assert g.label_rotation(mid) == pytest.approx(expect, abs=1e-6)


@pytest.mark.parametrize("mid", range(0, 360, 15))
def test_label_rotation_in_readable_range(mid):
    """Never mirrored. The boundary is inclusive at both ends: a label at exactly
    +/-90 is vertical, which is fine; 180 would be upside-down, which is not."""
    r = g.label_rotation(mid)
    assert -90 <= r <= 90, f"{mid}deg -> {r}deg would render mirrored"


# ── the rest of the primitives ───────────────────────────────────────────
def test_segment_midangle():
    assert g.segment_midangle(0, 90) == 45


def test_hexagon_has_six_vertices():
    pts = g.hexagon(50, 50, 20).split()
    assert len(pts) == 6
    assert all(len(p.split(",")) == 2 for p in pts)


def test_hexagon_points_sit_on_the_radius():
    # Coordinates are emitted at 2dp, so the tolerance is the rounding, not the maths.
    for p in g.hexagon(50, 50, 20).split():
        x, y = (float(v) for v in p.split(","))
        assert math.hypot(x - 50, y - 50) == pytest.approx(20, abs=0.01)


def test_rounded_rect_is_closed():
    d = g.rounded_rect(0, 0, 100, 50, 8)
    assert d.startswith("M") and d.rstrip().endswith("Z")


def test_rounded_rect_zero_radius():
    assert "nan" not in g.rounded_rect(0, 0, 100, 50, 0).lower()


def test_smooth_line_passes_through_endpoints():
    pts = [(0, 0), (10, 20), (20, 5), (30, 25)]
    d = g.smooth_line(pts)
    assert d.startswith("M 0.00 0.00") or d.startswith("M 0 0")
    assert "nan" not in d.lower()


def test_smooth_line_single_point_is_safe():
    assert "nan" not in g.smooth_line([(5, 5)]).lower()


def test_elbow_connector_is_a_right_angle_route_not_a_bezier_fan():
    """known-issues.md #6: a smooth bezier fanning sideways strikes the arrowhead at an
    angle instead of entering its flat back edge, so connectors are rounded right-angle
    elbows. This is the left-to-right variant — H, then V, then H — so the assertion is
    that the route is axis-aligned, not that any particular leg is vertical."""
    d = g.elbow_connector(0, 0, 100, 80)
    assert " H " in d and " V " in d, "expected an axis-aligned elbow route"
    assert " C " not in d, "a cubic bezier here is the fan-out shape #6 rules out"


def test_text_arc_reverse_flips_direction():
    a = g.text_arc(100, 100, 50, 0, 90)
    b = g.text_arc(100, 100, 50, 0, 90, reverse=True)
    assert a != b
