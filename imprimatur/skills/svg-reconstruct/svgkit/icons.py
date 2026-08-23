"""Icon placement.

Icons are NOT decorative filler — reconstruct them with the same care as
everything else. This module ships a curated set of real Lucide outline
paths (24x24 viewBox, the same icon set design-system's SKILL.md
mandates: "Lucide outline only — 1.5-2px stroke, round caps") as the
DEFAULT resolver, so the skill works standalone with no external wiring.

If the orchestrator wants a different or larger icon source later, it can
still override via set_resolver(fn) — that extension point is preserved —
but for this pipeline the built-in set below should cover the large
majority of business/data/tech diagram icons. Extend _ICONS directly when a
reconstruction needs one that's missing; keep entries as real Lucide path
data, not simplified placeholders (see CLAUDE.md's icon-fidelity rule).
"""

# name -> inner SVG markup (paths only, no outer <svg>), 24x24 viewBox,
# stroke-drawn (fill="none", caller sets stroke color).
_ICONS = {
    "search": '<circle cx="10" cy="10" r="7"/><path d="m21 21-6-6"/>',
    "map": '<path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>',
    "flask": '<path d="M9 3h6"/><path d="M10 3v6.5a2 2 0 0 1-.4 1.2L5 17a2 2 0 0 0 1.6 3.2h10.8a2 2 0 0 0 1.6-3.2l-4.6-6.3a2 2 0 0 1-.4-1.2V3"/>',
    "bar-chart-3": '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    "trending-up": '<polyline points="3 17 9 11 13 15 21 7"/><polyline points="14 7 21 7 21 14"/>',
    "shopping-cart": '<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/>',
    "message-square": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "alert-triangle": '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    "cloud": '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "shield-check": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "user": '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
    "user-check": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><polyline points="16 11 18 13 22 9"/>',
    "lightbulb": '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.4 1 2.3h6c0-.9.4-1.8 1-2.3A7 7 0 0 0 12 2z"/>',
    "award": '<circle cx="12" cy="8" r="6"/><path d="M15.5 13 17 22l-5-3-5 3 1.5-9"/>',
    "check-circle": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    "circle-check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "layout-grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "file-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    "arrow-right": '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    "chevrons-right": '<polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "flag": '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
    "rocket": '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>',
    "hammer": '<path d="m15 12-8.5 8.5a2.12 2.12 0 1 1-3-3L12 9"/><path d="M17.64 15 22 10.64"/><path d="m20.91 11.7-1.25-1.25c-.6-.6-.93-1.4-.93-2.25v-.86L16.01 4.6a5.56 5.56 0 0 0-3.94-1.64H9l.92.82A6.18 6.18 0 0 1 12 8.4v1.56l2 2h2.47l2.26 1.91"/>',
    "pencil-ruler": '<path d="m14.622 17.897-10.68-2.913"/><path d="M18.376 2.622a1 1 0 1 1 3.002 3.002L17.36 9.643a.5.5 0 0 1-.706 0l-2.29-2.29a.5.5 0 0 1 0-.707z"/><path d="m8 6 2-2"/><path d="m18 16 2-2"/><path d="m17 11-4.5 4.5"/><path d="M3 21v-3.5L14 6l3.5 3.5L7 21z"/>',
    "clipboard-list": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>',
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "search-check": '<path d="m8 11 2 2 4-4"/><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "credit-card": '<rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "code": '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "dollar-sign": '<line x1="12" y1="2" x2="12" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "heart": '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "chart-line": '<path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>',
    "handshake": '<path d="m11 17 2 2a1 1 0 1 0 3-3"/><path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4"/><path d="m21 3 1 11h-2"/><path d="M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3"/><path d="M3 4h8"/>',
    # --- compound icons, not single Lucide glyphs (no exact Lucide match
    # exists for these) — built from Lucide-style stroke primitives to stay
    # visually consistent with the rest of the set. Added for the donut
    # slide-8 reconstruction: bar-chart-trend (Measurable Value), lightbulb-
    # rays (Knowledge), hands-cradling-person (Ownership), shield-people
    # (Governance). Flagged individually, see icon-fidelity notes in
    # references/embedding-example.md.
    "bar-chart-trend": (
        '<path d="M3 21h18"/><path d="M7 21v-7"/><path d="M12 21v-11"/>'
        '<path d="M17 21v-15"/><path d="M6 10 11 6 16 3" stroke-dasharray="2 2"/>'
        '<circle cx="6" cy="10" r="1.2" fill="#fff" stroke="none"/>'
        '<circle cx="11" cy="6" r="1.2" fill="#fff" stroke="none"/>'
        '<circle cx="16" cy="3" r="1.2" fill="#fff" stroke="none"/>'
    ),
    "lightbulb-rays": (
        '<path d="M9 18h6"/><path d="M10 22h4"/>'
        '<path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.4 1 2.3h6c0-.9.4-1.8 1-2.3A7 7 0 0 0 12 2z"/>'
        '<path d="M12 0v1.8"/><path d="M3.5 3.5l1.3 1.3"/>'
        '<path d="M20.5 3.5l-1.3 1.3"/><path d="M1 9h1.8"/><path d="M21.2 9H23"/>'
    ),
    "hands-cradling-person": (
        '<circle cx="12" cy="7" r="2.5"/>'
        '<path d="M8.5 12c0-1.5 1.5-2.5 3.5-2.5s3.5 1 3.5 2.5"/>'
        '<path d="M2 17c0-2 1.5-3.5 4-3.5 1 0 1.8.3 2.5 1"/>'
        '<path d="M22 17c0-2-1.5-3.5-4-3.5-1 0-1.8.3-2.5 1"/>'
        '<path d="M2 17c1 2 3 3 5 3"/><path d="M22 17c-1 2-3 3-5 3"/>'
    ),
    "shield-people": (
        '<path d="M12 22s7-3.2 7-9V5.5l-7-2.5-7 2.5V13c0 5.8 7 9 7 9z"/>'
        '<path d="m9.3 9 1.7 1.7L14.7 7"/>'
        '<circle cx="8.5" cy="15" r="1.3"/><circle cx="12" cy="15" r="1.3"/>'
        '<circle cx="15.5" cy="15" r="1.3"/>'
        '<path d="M6.5 19c.3-1.2 1-2 2-2"/><path d="M17.5 19c-.3-1.2-1-2-2-2"/>'
        '<path d="M9.5 19.5c.6-1 1.4-1.5 2.5-1.5s1.9.5 2.5 1.5"/>'
    ),
    # Filled bust + badge — deviates from the outline-only Lucide icon
    # rule on purpose, to match the reference's filled-silhouette style.
    # Flag this in review: swap to outline "user-check" if brand-audit
    # flags it on a real slide.
    "user-badge-filled": (
        '<circle cx="12" cy="7.5" r="4.2" fill="#fff" stroke="none"/>'
        '<path d="M4.5 21c0-4.5 3.2-7 7.5-7s7.5 2.5 7.5 7" fill="#fff" stroke="none"/>'
        '<circle cx="18" cy="18.5" r="4" fill="{DEEP}" stroke="#fff" stroke-width="1.5"/>'
        '<path d="m16.3 18.5 1.2 1.2 2.2-2.4" stroke="#fff" stroke-width="1.5" fill="none"/>'
    ),
}

_resolver = None  # optional override; if unset, default_resolver is used


def set_resolver(fn):
    """fn(name:str, size:int, color:str) -> str (inner SVG markup).
    Optional — the module works out of the box via default_resolver()."""
    global _resolver
    _resolver = fn


def has_resolver():
    return _resolver is not None


def default_resolver(name, size=None, color=None):
    if name not in _ICONS:
        raise KeyError(
            f"Unknown icon '{name}'. Available: {sorted(_ICONS)}. "
            f"Add a real Lucide path to svgkit/icons.py._ICONS — "
            f"never substitute a cruder placeholder shape."
        )
    return _ICONS[name]


def place(name, x, y, size, color="#fff", stroke_width=None):
    """Position an icon centered on (x, y). Uses the injected resolver if
    set, else the built-in curated Lucide set."""
    # presets is imported here rather than at module scope: it loads the design system,
    # and svgkit/__init__ imports icons before presets exists.
    from . import presets
    stroke_width = stroke_width if stroke_width is not None else presets.STROKE_WIDTH
    resolver = _resolver or default_resolver
    inner = resolver(name, size, color)
    # A couple of icons carry a filled accent detail. They name a ROLE rather than a hex,
    # so the same icon set works for any pack — resolved here, where presets is available.
    if "{DEEP}" in inner:
        inner = inner.replace("{DEEP}", presets.DEEP)
    scale = size / 24.0
    tx = x - size / 2
    ty = y - size / 2
    return (
        f'<g transform="translate({tx:.2f} {ty:.2f}) scale({scale:.4f})" '
        f'fill="none" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round">{inner}</g>'
    )


def available():
    return sorted(_ICONS)
