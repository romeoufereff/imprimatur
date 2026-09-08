# Recipe: Funnel Chart

## When to use
Stacked descending trapezoids showing stage-to-stage drop-off
(e.g., conversion funnel: visitors -> leads -> customers).

## Config schema
See configs/example_funnel.json. A stage with neither `stops` nor `color` gets
`presets.sequential_stops(i, n)` automatically — real per-stage hue variation,
not a flat fill. Set `stops` explicitly only to match a reference's exact colors.

## Build steps
1. Width of each band's top scales to its value / max value
   (between min_width and max_width). Bottom width uses next stage's value.
2. Each band = centered trapezoid polygon.
3. Icon left-inset; label + formatted value centered.

## Failure checks
- widths shrink monotonically top-to-bottom
- value formatting (thousands separators) matches
- gap between bands consistent
- gradient vs flat matches the reference; an unverified flat stage should not
  be a literal two-identical-stop "gradient" — either a real reference-matched
  flat `color`, or let the default sequential gradient apply
