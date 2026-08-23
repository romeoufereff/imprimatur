"""Gradient <defs> builders.

Rule: assume gradients until proven flat. Inspect every colored region in
the reference screenshot before deciding a fill is a solid color — diagonal
light-to-dark shading, glowing centers, and soft highlights are gradients,
not single hex values. See presets.py for the active pack's canonical brand gradient
and per-segment tints so recipes default to on-brand fills automatically.
"""
import math


def linear(id_, angle_deg, stops):
    """stops = [(offset, color, opacity), ...]  offset like '0%'."""
    a = math.radians(angle_deg)
    x1, y1 = 50 - 50 * math.cos(a), 50 - 50 * math.sin(a)
    x2, y2 = 50 + 50 * math.cos(a), 50 + 50 * math.sin(a)
    s = "".join(
        f'<stop offset="{o}" stop-color="{c}" stop-opacity="{op}"/>'
        for o, c, op in stops
    )
    return (
        f'<linearGradient id="{id_}" x1="{x1:.1f}%" y1="{y1:.1f}%" '
        f'x2="{x2:.1f}%" y2="{y2:.1f}%">{s}</linearGradient>'
    )


def radial(id_, stops, cx="50%", cy="50%", r="50%", fx=None, fy=None):
    focal = ""
    if fx is not None and fy is not None:
        focal = f' fx="{fx}" fy="{fy}"'
    s = "".join(
        f'<stop offset="{o}" stop-color="{c}" stop-opacity="{op}"/>'
        for o, c, op in stops
    )
    return (
        f'<radialGradient id="{id_}" cx="{cx}" cy="{cy}" r="{r}"{focal}>'
        f"{s}</radialGradient>"
    )


def auto(id_, base_color, angle=135, light=0.22, dark=-0.14):
    """Default gradient for a builder that only has ONE color to paint a shape with.
    Shades base_color into a light/dark pair (see presets._shade) instead of the
    flat-fill-disguised-as-a-gradient antipattern of writing the same color into both
    stops. Use this as a DEFAULT; a flat fill actually verified against a reference
    screenshot should still be written explicitly as two identical stops, not routed
    through here — this is for the no-reference / no-explicit-color-chosen case."""
    from . import presets
    return linear(id_, angle, [("0%", presets._shade(base_color, light), 1),
                               ("100%", presets._shade(base_color, dark), 1)])


def drop_shadow(id_, dx=0, dy=4, blur=6, color="#000", opacity=0.25):
    return (
        f'<filter id="{id_}" x="-50%" y="-50%" width="200%" height="200%">'
        f'<feDropShadow dx="{dx}" dy="{dy}" stdDeviation="{blur}" '
        f'flood-color="{color}" flood-opacity="{opacity}"/></filter>'
    )
