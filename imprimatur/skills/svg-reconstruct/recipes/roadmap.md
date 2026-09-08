# Recipe: Roadmap / Swimlane Timeline

## When to use
Grid of lanes (rows) x time columns, with items spanning one or more
columns within a lane. Product/project roadmaps.

## Config schema
See configs/example_roadmap.json. An item with neither `stops` nor `color`
gets `gradients.auto(id, presets.PRIMARY)` — a real light/dark gradient on ONE
hue, not a rainbow: bars are individual initiatives, not categories, so they
stay one consistent hue by default (set explicit `color`/`stops` per item to
color-code by team/status).

## Coordinate convention
- col is 0-indexed into columns[]. span = number of columns the bar covers.
- lane must match an entry in lanes[]; row index derived from its position.

## Build steps
1. Draw column headers above the grid.
2. Draw alternating lane background stripes with lane labels on the left.
3. Draw item bars: x from origin + lane_label_width + col*col_width,
   width = span*col_width (with inset), rounded-rect fill + centered label.

## Failure checks
- items align to their lane row and start column
- span widths cover the correct number of columns
- alternating lane stripes match original
- column headers aligned with column centers
