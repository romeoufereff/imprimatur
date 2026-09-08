# Recipe: Pie Chart (full disc, optional exploded slices)

## Config schema
See configs/example_pie.json. A slice with neither `stops` nor `color` gets
`presets.sequential_stops(i, n)` automatically — real per-slice hue variation,
not a flat fill.

## Build steps
1. sum values -> angle per slice
2. geometry.arc_segment with r_in=0 (full slice — handled as a true pie
   wedge, not a very-thin donut)
3. explode: shift slice center along mid-angle by explode px
4. labels inside (mid-radius) or outside (leader radius)

## Failure checks
- angles sum to 360; start_angle honored
- gradient vs flat per slice matches the reference; an unverified flat slice
  should be a literal flat `color`, not a two-identical-stop "gradient"
- percent formatting matches
