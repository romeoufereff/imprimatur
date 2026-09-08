# Recipe: Gauge / Radial Progress

## When to use
Single value shown as a filled arc against a track, with a large numeric
readout in the center. Semi-circular or wide-arc.

## Config schema
See configs/example_gauge.json. The value arc defaults to
`gradients.auto(id, presets.PRIMARY)` (a real light/dark gradient on one hue)
when neither `stops` nor `value_color` is given — never a flat single-tone
fill by default; set `value_color` explicitly for a reference-verified flat.

## Angle convention
- Angles in degrees, 0 = top, clockwise (svgkit.polar convention).
- start_angle typically negative (left of top), end_angle positive.

## Build steps
1. Track arc: arc_segment(r_in, r_out, start, end) with rounded caps
   (corner = (r_out-r_in)/2).
2. Value arc: same but end = start + fraction*(end-start).
3. Center: large display text + optional subtitle below.

## Failure checks
- track spans full start->end; value arc is a subset
- rounded arc caps match original
- value maps correctly (value=max fills the whole track)
- gradient direction along the arc matches; the value arc reads as having
  real depth, not a flat single tone, unless the reference proves it's flat
