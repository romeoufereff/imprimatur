# Worked example: embedding a donut reconstruction into a deck slide

This walks through the exact case that motivated this skill — a client deck
slide 8, "Data products are the building blocks" — redone with `svgkit`
instead of hand-authored paths, so the difference is concrete.

## What happened without this skill

1. Round 1: labels placed horizontally at a fixed radius. Text overflowed
   past the segment edges on the side wedges ("Expert knowledge",
   "Users & personas") because a straight horizontal label at 30-40px wide
   per character doesn't fit inside a 72°-wide wedge at any reasonable
   radius without either shrinking the font (against brand minimums) or
   overflowing.
2. Round 2: pushed the label radius outward to give more room. Fixed the
   overflow but now labels floated visually disconnected from their wedge.
3. Round 3: rotated each label to follow the wedge's tangent angle
   (computed by hand, ad hoc, in the same script — not reusable). This is
   what finally matched the reference.

Three rounds, ~15 minutes, and the tangent-rotation math was written once
and thrown away — the next radial diagram would start from zero again.

## The same result with svgkit

**MEASURE** (Build Spec, from the reference screenshot):
- Canvas: 900×570 (matching the slide's right-panel content area)
- Center (450, 285), r_inner=158, r_outer=258, corner=0 (reference has
  sharp segment edges, not rounded — verified by looking closely at the
  screenshot, not assumed)
- 5 segments, 72° each, 6° gap between (`SPAN = 72 - GAP`)
- Gradient: brand blue-to-navy per segment (`presets.WEDGE_SEQUENCE`),
  hub: purple radial (`presets.HUB_GRADIENT_STOPS`)
- Icons: bar-chart-3, lightbulb, award, shield-check, user-check — all in
  the built-in set, no new paths needed
- Labels: straight (not curved textPath — verified against the reference:
  the text sits on a straight baseline, just rotated, not bending along
  the arc), rotated via `geometry.label_rotation(mid_angle)`

**Config** (`configs/deck-slide8-data-products.json`):

```json
{
  "type": "donut", "width": 900, "height": 570,
  "center": [450, 285], "r_inner": 158, "r_outer": 258, "corner": 0,
  "hub": {"label": "Data", "radius": 128,
          "gradient": ["role:accent", "role:accent"], "font_size": 30},
  "segments": [
    {"start": 54, "end": 126, "stops": [["0%","role:primary-mid",1],["100%","role:primary-mid",1]],
     "label": {"text": "Measurable value", "radius": 206, "rotate_to_arc": true},
     "icon": {"name": "bar-chart-3", "radius": 228}},
    {"start": -18, "end": 54, "stops": [["0%","role:primary",1],["100%","role:deep",1]],
     "label": {"text": "Expert knowledge", "radius": 206, "rotate_to_arc": true},
     "icon": {"name": "lightbulb", "radius": 228}},
    {"start": -90, "end": -18, "stops": [["0%","role:primary",1],["100%","role:deep",1]],
     "label": {"text": "Ownership", "radius": 206, "rotate_to_arc": true},
     "icon": {"name": "award", "radius": 212}},
    {"start": 198, "end": 270, "stops": [["0%","role:primary",1],["100%","role:deep",1]],
     "label": {"text": "Governance", "radius": 206, "rotate_to_arc": true},
     "icon": {"name": "shield-check", "radius": 212}},
    {"start": 126, "end": 198, "stops": [["0%","role:primary",1],["100%","role:deep",1]],
     "label": {"text": "Users & personas", "radius": 206, "rotate_to_arc": true},
     "icon": {"name": "user-check", "radius": 228}}
  ]
}
```

Note angles use this module's 0°=top convention, not the ad-hoc convention
from the live fix — see `svgkit/geometry.py`'s `polar()` docstring.

**Build + verify:**

```python
from recipes.registry import get_builder
from svgkit import render

build = get_builder("donut")
history = render.verify_loop(
    build, "configs/deck-slide8-data-products.json",
    original_png="reference/slide8_target.png",
    out_dir="configs/_verify", width=900, height=570,
)
```

Because the geometry (segment bounds, label radius, tangent rotation) is
computed from the config, not hand-tuned, this converges in round 1 or 2 —
not round 3 — and the config is reusable if the wedge count, labels, or
colors need to change later (edit JSON, rerun; no path math to redo).

## Embedding into the host slide template

The donut recipe's `build()` returns a standalone `<svg>` document. The
slide template — whichever two-panel host the active pack provides, per
`scripts/pack_inventory.py` — expects a fragment inside its own
`<svg viewBox="0 0 900 570" style="width:100%;height:100%">` — so:

1. Regenerate with `canvas.fragment()` instead of `canvas.svg()` (or just
   strip the outer `<svg ...>...</svg>` tags from the built file — the
   `<defs>` and body content are what get emBEDDED).
2. Check id collisions: the donut recipe's gradients are named `seg0..4`
   and `hub` — these won't collide with the host template's own
   `grad-box`/`grad-tint` ids from the pipeline snippet, but if the host
   slide's chrome (e.g. the footer logo `<svg>`) is in the *same* DOM and
   also defines an id like `hub`, rename before merging.
3. Because the config's `width`/`height` (900×570) was set to match the
   host's content-area viewBox exactly (see MEASURE step above), no
   rescaling transform is needed — this is why matching the target
   viewBox during MEASURE, not after, saves a step.
4. Run `deck-designer`'s density/focal-point self-check, then
   `brand-audit` (token check — this config already only uses
   `svgkit.presets` values, so it should pass on the first try) and
   `design-crit`.
