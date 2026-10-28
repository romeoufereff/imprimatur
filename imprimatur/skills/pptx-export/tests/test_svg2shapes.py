"""svg2shapes / build_pptx regressions — run from validate_all.sh (pytest, no browser).

  href-inherited gradients   a <linearGradient> that carries only geometry and points at
                             another one with xlink:href/href inherits its stops and every
                             attribute it does not set (2026-10-22: client cover + agenda
                             orbit artwork exported as svgBlip pictures — the stop list came
                             out empty and `_paints` raised IndexError on the stroke).
  degenerate gradients       zero stops paint nothing, one stop paints solid, an href cycle
                             terminates.
  builder rollback           a model node that fails half-way leaves no stray shapes behind
                             for the picture fallback to sit on (2026-10-22: two freeforms
                             under the agenda svgBlip).
  chart or diagram           provenance decides, not size: a dense hand-drawn diagram
                             converts, an ECharts SVG stays a picture, data-pptx overrides
                             both, and only illustration-sized artwork hits the ceiling
                             (2026-10-23: the 1&1 knowledge-graph row, 180 elements, hit the
                             old 150 cap while a 42-element ECharts chart converted).
"""
import os
import sys
import xml.etree.ElementTree as ET

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import svg2shapes  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "href-gradient.svg")
RECT = {"x": 0, "y": 0, "w": 400, "h": 200}
# expected colours come from the fixture itself — no hex literals in engine code
# (check_engine_clean.py scans every .py in the plugin)
_DEFS = {g.get("id"): g for g in ET.parse(FIXTURE).getroot().iter() if g.get("id")}


def _stop_colors(gid):
    return [s.get("stop-color").upper() for s in _DEFS[gid] if s.tag.endswith("stop")]


@pytest.fixture(scope="module")
def parser():
    p = svg2shapes.Parser(ET.parse(FIXTURE).getroot(), RECT)
    p.collect_defs(p.root)
    return p


@pytest.fixture(scope="module")
def nodes():
    return svg2shapes.convert(FIXTURE, RECT)


def test_href_stroke_converts_instead_of_raising(nodes):
    ring = nodes[0]
    assert ring["t"] == "ellipse" and ring["fill"] is None
    assert ring["stroke"]["grad"] is not None, "inherited gradient stroke kept as line gradFill"
    stops = ring["stroke"]["grad"]["stops"]  # userSpaceOnUse: cut to the circle's slice
    assert len(stops) >= 2 and stops[0][1] == _stop_colors("base")[0]
    assert ring["stroke"]["color"] == _stop_colors("base")[1]  # mid-stop solid fallback


def test_href_inherits_units_and_keeps_local_geometry(parser):
    ring = parser.gradients["ring"]
    assert ring["units"] == "user", "gradientUnits comes from the referenced gradient"
    assert ring["p1"] == (40.0, 0.0) and ring["p2"] == (360.0, 0.0), "local x1/x2 win"


def test_href_chain_two_hops_inherits_geometry(parser, nodes):
    hop2 = parser.gradients["hop2"]
    assert len(hop2["stops"]) == 3 and hop2["units"] == "user"
    assert hop2["p1"] == (40.0, 0.0), "geometry inherited from the nearest gradient that sets it"
    assert nodes[1]["fill"]["kind"] == "grad"


def test_local_stops_win(parser):
    assert [s[1] for s in parser.gradients["own"]["stops"]] == _stop_colors("own")


def test_zero_stop_stroke_paints_nothing(nodes):
    empty = nodes[3]
    assert empty["fill"]["color"] == "#FFFFFF" and empty["stroke"] is None


def test_one_stop_paints_solid(nodes):
    one = nodes[4]
    assert one["fill"] == {"kind": "solid", "color": "#123456", "alpha": 1.0}
    assert one["stroke"]["color"] == "#123456" and one["stroke"]["grad"] is None


def test_href_cycle_terminates_and_paints_nothing(parser, nodes):
    assert parser.gradients["cyc-a"]["stops"] == []
    assert nodes[5]["fill"] is None


def test_builder_rolls_back_partial_group():
    from pptx import Presentation
    import build_pptx

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    before = len(slide.shapes)
    good = {"t": "rect", "x": 0, "y": 0, "w": 10, "h": 10,
            "fill": {"kind": "solid", "color": "#000000", "alpha": 1.0},
            "stroke": None, "shadow": None}
    bad = dict(good, t="ellipse", fill={"kind": "grad", "stops": [], "angle": 0})
    with pytest.raises(Exception):
        build_pptx.add_svg_shape_group(slide, [good, good, bad], RECT)
    assert len(slide.shapes) == before, "no stray shapes left for the picture fallback"


def _dense_svg(tmp_path, n, **attrs):
    """n circles + n lines, the shape of the 1&1 knowledge-graph row."""
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    body = "".join(f'<circle cx="{4 * i}" cy="20" r="2" fill="navy"/>'
                   f'<line x1="{4 * i}" y1="20" x2="{4 * i + 4}" y2="30" stroke="navy"/>'
                   for i in range(n))
    p = tmp_path / f"dense-{n}-{len(attrs)}.svg"
    p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="40"{extra}>'
                 f"{body}</svg>")
    return str(p)


def test_dense_hand_drawn_diagram_converts(tmp_path):
    nodes = svg2shapes.convert(_dense_svg(tmp_path, 90), RECT)  # 180 paint elements
    assert len(nodes) == 180


def test_echarts_svg_stays_a_picture(tmp_path):
    with pytest.raises(svg2shapes.Unconvertible, match="echarts chart"):
        svg2shapes.convert(_dense_svg(tmp_path, 5, data_pptx_chart="echarts"), RECT)


def test_author_marks_win(tmp_path):
    with pytest.raises(svg2shapes.Unconvertible, match='data-pptx="picture"'):
        svg2shapes.convert(_dense_svg(tmp_path, 5, data_pptx="picture"), RECT)
    chart = _dense_svg(tmp_path, 5, data_pptx_chart="echarts", data_pptx="shapes")
    assert len(svg2shapes.convert(chart, RECT)) == 10


def test_ceiling_and_override(tmp_path):
    n = svg2shapes.MAX_ELEMENTS // 2 + 1
    with pytest.raises(svg2shapes.Unconvertible, match="paint elements"):
        svg2shapes.convert(_dense_svg(tmp_path, n), RECT)
    assert len(svg2shapes.convert(_dense_svg(tmp_path, n, data_pptx="shapes"), RECT)) == 2 * n
