# Recipe: Segmented Donut / Radial Diagram

## When to use
A ring divided into N wedge segments around a central hub — the "5-6
labeled arcs around a circle with a word in the middle" pattern (data
product wheels, capability wheels, maturity wheels).

## Config schema
See configs/example_donut.json. Key fields:
- `center` [cx, cy], `r_inner`, `r_outer`, `corner` (corner radius in px)
- `hub`: {label, radius, gradient:[start,end] (2 DIFFERENT colors — omit to
  get an accent→deep default), font_size, color}
- `segments[]`: {start, end (degrees, 0=top clockwise), gradient_angle,
  stops (omit to get `presets.sequential_stops(i, n)` — a real per-segment
  gradient with hue variety, not one flat hue repeated), label:{text | lines,
  size, radius, curve}, icon:{name, size, radius}}
- `label.curve`: leave unset for reconstructions with no reference to verify
  against — the builder auto-decides curved vs straight per line via
  `text.curve_legible` (see Build step 3). Only set it explicitly (`true`/
  `false`) once MEASURE has confirmed the reference's actual treatment.

## Build steps
1. Compute segment count, per-segment start/end angle, and the gap between
   them BEFORE writing any path — state this explicitly (see SKILL.md).
2. Each segment via geometry.arc_segment(r_in, r_out, start, end, corner),
   filled via `presets.sequential_stops(i, n)` unless the config supplies
   its own `stops` (e.g. matching a reference's exact colors).
3. Label: `text.smart_label` picks curved-on-arc vs straight-tangent-rotated
   per line based on whether the arc at that radius/span can actually hold
   the text at its font size without warping (`text.curve_legible`) — do not
   force `curve:true` by default; the skill's own origin-story rebuild
   converged on straight rotated labels for exactly this reason. Only pass
   an explicit `force` (via the config's `curve` field) once a reference
   screenshot has confirmed true curved text is what's shown.
4. Icon centered inside the segment body via icons.place.
5. Hub: radial gradient circle (two DIFFERENT colors — a flat hub reads as
   a puck, not a focal point) + centered label + a soft drop-shadow for
   depth (`gradients.drop_shadow`) so the hub sits visually above the ring.

## Failure checks
- Every segment's start/end sums correctly around the full ring (or the
  intentional gap) — no overlap, no drift.
- Corner rounding present if the reference shows rounded segment ends.
- Labels stay within their segment's angular span at the chosen radius —
  if a label overflows into the next segment, increase its radius or the
  segment's angular span, don't shrink the font below presets.MIN_LABEL_PX.
- No segment or the hub renders as a flat single-tone fill unless a
  reference screenshot specifically proves it's flat (see SKILL.md Design
  Principles: Depth) — check the rendered SVG, not just the config.
- Adjacent segments read as distinguishable hues, not one color repeated
  around the ring, unless the reference is genuinely monochrome.
