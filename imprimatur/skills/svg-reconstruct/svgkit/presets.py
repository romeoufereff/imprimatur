"""Design-system defaults for the SVG builder, read from the ACTIVE pack.

Every constant below used to be a hand-copied hex from one brand's Tailwind config,
which meant swapping design systems silently left generated diagrams on the old
brand. Now the values resolve at import time through the plugin's scripts/ds_config.py:
colors come from the pack's `roles` map (role -> its own token -> hex), and the
gradient/geometry values from the pack's `svg` block in design-system.json.

The public names are unchanged, so recipes and builders keep working — they just
paint in whatever brand is active.

Do NOT invent new hex values here. If a reconstruction needs a color no role
provides, that is a signal to flag it to the user (or to add a role to the pack's
manifest), not to hardcode a constant in engine code.
"""

import os
import sys

# Depth-independent: anchor on the plugin marker rather than counting `..` hops.
_here = os.path.dirname(os.path.abspath(__file__))
_probe = _here
while not os.path.isdir(os.path.join(_probe, ".claude-plugin")):
    _parent = os.path.dirname(_probe)
    if _parent == _probe:
        raise RuntimeError(f"No .claude-plugin/ found above {_here}")
    _probe = _parent
_SCRIPTS = os.path.join(_probe, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from ds_config import load  # noqa: E402

_ds = load()


def resolve_role(name, default=None):
    """Look up a role by the pack's OWN manifest name ('primary', 'accent', ...),
    not a presets.* constant name. This is what schema.load_config's 'role:<name>'
    config indirection calls — the config-file equivalent of every other engine
    surface asking the pack for a role instead of a literal."""
    return _ds.color(name, default)


def resolve_role_list(name, default=None):
    """List-valued counterpart of resolve_role, for roles like 'viz'/'vizExtended'."""
    return _ds.palette(name, default or [])

# Fallbacks for roles a pack does not fill. These are deliberately achromatic: the module
# docstring's rule is "do not invent hex values here", and the previous defaults broke it
# quietly: they were the *default* pack's real colours. That reads as harmless — until a
# different pack is loaded, leaves a role unfilled, and the diagram silently paints in
# another brand's blue, which validate.py then rejects as off-palette. Grey is visibly a
# placeholder; a plausible blue is not. If a reconstruction needs a colour no role
# provides, flag it or add the role to the pack — do not restore a literal here.
_NEUTRAL_INK = "#1A1A1A"
_NEUTRAL_MUTED = "#6A6A6A"
_NEUTRAL_RULE = "#D0D0D0"
_NEUTRAL_SURFACE = "#F5F5F5"

# Single-quoted, not double: every caller interpolates this into a
# double-quoted SVG attribute (font-family="{family}"). Double-quoted font
# names here would collide with the attribute's own quotes and truncate
# the value at the first embedded '"' — a real bug caught by actually
# rendering output (text silently fell back to the browser default serif
# font on every label) rather than by reading the code. A pack that declares
# svg.fontStack is responsible for keeping that convention.
FONT_FAMILY = _ds.get("svg.fontStack", "sans-serif")

# Primary palette (semantic roles, not brand color names)
BLUE = PRIMARY = _ds.color("primary", _NEUTRAL_INK)
BLUE_MID = PRIMARY_MID = _ds.color("primary-mid", BLUE)
PURPLE = ACCENT = _ds.color("accent", BLUE)
NAVY = DEEP = _ds.color("deep", BLUE)
TEAL = SUPPORT_1 = _ds.color("support-1", BLUE)
CYAN = SUPPORT_2 = _ds.color("support-2", BLUE)

# Extended (charts & dataviz only — never structural UI, per brand rules).
# Sourced from the pack's vizExtended role list; a pack that declares fewer
# extended colors simply exposes fewer distinct values here.
_EXT = _ds.palette("vizExtended", [])


def _ext(i, fallback):
    return _EXT[i] if i < len(_EXT) else fallback


GREEN = _ext(0, BLUE)
ORANGE = _ext(1, ACCENT)
RED = _ext(2, ACCENT)
SKY = _ext(3, BLUE_MID)
SLATE = _ext(4, DEEP)
LAVENDER = _ext(5, ACCENT)

# Chart series order — the pack decides which roles read well side by side.
VIZ_SEQUENCE = _ds.palette("viz", [BLUE, TEAL, CYAN, PURPLE])

# Semantic text / structure
TEXT = INK = _ds.color("ink", _NEUTRAL_INK)
BODY = _ds.color("body", TEXT)
MUTED = _ds.color("muted", _NEUTRAL_MUTED)     # WCAG-safe at any size
MUTED_SOFT = _ds.color("muted-soft", MUTED)    # decorative / >=18px only
RULE = _ds.color("rule", _NEUTRAL_RULE)
LIGHT_BLUE = TINT = _ds.color("tint", _NEUTRAL_SURFACE)
SURFACE = _ds.color("surface", _NEUTRAL_SURFACE)


def _stops(key, default):
    """Manifest gradient stops arrive as JSON lists; builders expect tuples."""
    raw = _ds.get(key)
    if not isinstance(raw, list) or not raw:
        return default
    return [tuple(s) for s in raw]


# The brand gradient, as stops rather than a CSS string (SVG has no linear-gradient()).
BRAND_GRADIENT_STOPS = _stops("svg.brandGradientStops",
                              [("0%", BLUE_MID, 1), ("80%", BLUE, 1), ("100%", PURPLE, 1)])
# svgkit's angle convention differs from CSS; the pack tunes this to visually match
# its own CSS brand gradient.
BRAND_GRADIENT_ANGLE = _ds.get("svg.brandGradientAngle", 150)

# Tint pair for "future / inactive" segments
TINT_GRADIENT_STOPS = _stops("svg.tintGradientStops",
                             [("0%", LIGHT_BLUE, 1), ("100%", LIGHT_BLUE, 1)])

# Status colours. A pack that declares no status roles gets achromatic values rather than
# a borrowed red/green — an unfilled role should look unfilled, not like a decision.
POSITIVE = _ds.color("positive", _NEUTRAL_MUTED)
CAUTION = _ds.color("caution", _NEUTRAL_MUTED)
NEGATIVE = _ds.color("negative", _NEUTRAL_INK)

# Solid foundation fill (used for base/foundation bands)
FOUNDATION_FILL = NAVY

# Hub/focal radial gradient (matches the donut/hub_spoke center convention)
HUB_GRADIENT_STOPS = _stops("svg.hubGradientStops",
                            [("0%", PURPLE, 1), ("100%", NAVY, 1)])

# Sequential wedge palette for donut/pie/radial diagrams with more segments than the
# 3-stop brand gradient reads well across — so a 5+ segment wheel still reads as one
# family. Packs that don't declare one fall back to repeating the brand gradient.
_WEDGES = _ds.get("svg.wedgeSequence")
WEDGE_SEQUENCE = ([[tuple(s) for s in wedge] for wedge in _WEDGES]
                  if isinstance(_WEDGES, list) and _WEDGES else [BRAND_GRADIENT_STOPS])

# Minimum type sizes. svgkit does not enforce these automatically — the designer
# self-check and brand-audit are the actual gates — but recipes should not default
# below them without a documented reason. Since 2026-10-06 validate.py applies the
# pack's PROSE floor (typography.minFontSizePx) to SVG text too, so every tier is
# clamped to it: a pack may size its tiers above the floor, never below (the EPAM
# pack's old 16/14 label/caption tiers produced diagrams that then failed the audit).


def _tier(key, default, floor):
    v = _ds.get(key, default)
    try:
        v = float(v)
    except (TypeError, ValueError):
        v = float(default)
    v = max(v, floor)
    return int(v) if v == int(v) else v


_PROSE_FLOOR = float(_ds.get("typography.minFontSizePx", 14) or 14)
MIN_BODY_PX = _tier("svg.minBodyPx", 20, _PROSE_FLOOR)
MIN_LABEL_PX = _tier("svg.minLabelPx", 16, _PROSE_FLOOR)
MIN_CAPTION_PX = _tier("svg.minCaptionPx", _PROSE_FLOOR, _PROSE_FLOOR)

# Icon stroke width, matching the pack's icon rules.
STROKE_WIDTH = _ds.get("svg.iconStrokeWidth", 1.8)


def _shade(hex_color, amt):
    """Lighten (amt>0) or darken (amt<0) a resolved hex toward white/black.

    DEPRECATED for engine output — nothing in svgkit calls it any more. A computed shade
    is a colour the pack never declared, so every shaded stop failed the palette census
    on the slide that used it (2026-10-01: #2646C4 / #3B6BE6 / #6A5BD8 / #5E36A8-style
    stops). Use `partner()` / `sequential_stops()` — on-palette pairs — instead. Kept
    only so a hand-written config that still calls it does not crash."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color  # not a plain hex (named color, url()...) — leave it alone
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if amt >= 0:
        r, g, b = (r + (255 - r) * amt, g + (255 - g) * amt, b + (255 - b) * amt)
    else:
        r, g, b = (r * (1 + amt), g * (1 + amt), b * (1 + amt))
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(v))) for v in (r, g, b)))


def _ramp():
    """The pack's own colour order for two-tone pairs: the brand gradient's stops, then
    the viz series — every entry a declared colour, deduplicated, order kept."""
    seen, out = set(), []
    for c in [st[1] for st in BRAND_GRADIENT_STOPS] + list(VIZ_SEQUENCE):
        u = (c or "").upper()
        if u.startswith("#") and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def partner(hex_color):
    """On-palette second stop for a one-colour gradient: base's neighbour in the pack's
    brand ramp (418DFF→3055DA→8353D2→…), so a two-tone fill never invents a hex."""
    ramp = _ramp()
    base = (hex_color or "").upper()
    if base in ramp and len(ramp) > 1:
        i = ramp.index(base)
        brand = [st[1].upper() for st in BRAND_GRADIENT_STOPS]
        if base in brand and len(brand) > 1:      # stay inside the brand ramp: …→purple→blue
            j = brand.index(base)
            return brand[j + 1] if j + 1 < len(brand) else brand[-2]
        return ramp[(i + 1) % len(ramp)]
    return PRIMARY if base != PRIMARY.upper() else ACCENT


def sequential_stops(i, n, light=None, dark=None):
    """Per-item fill stops for the i-th of n items in a multi-segment radial/repeating
    diagram (donut wedges, pie slices, gauge fill, cycle nodes) — the default every such
    builder should reach for instead of a bare `presets.PRIMARY` flat fill or a config
    that repeats one role into both gradient stops.

    Prefers the pack's own authored `svg.wedgeSequence` (WEDGE_SEQUENCE) when it declares
    enough entries to cover all n items — that is real design-system intent about which
    exact stops read well together. Otherwise pairs each viz hue with its on-palette
    neighbour (`partner`). Never shades: a tint/shade is a colour the pack did not
    declare, and the palette census fails it (light/dark are accepted and ignored for
    old callers).
    """
    if len(WEDGE_SEQUENCE) >= n:
        return WEDGE_SEQUENCE[i % len(WEDGE_SEQUENCE)]
    hues = VIZ_SEQUENCE or [PRIMARY]
    base = hues[i % len(hues)]
    return [("0%", base, 1), ("100%", partner(base), 1)]
