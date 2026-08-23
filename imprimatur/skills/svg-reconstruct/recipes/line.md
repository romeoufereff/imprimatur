# Recipe: Line Chart (single/multi-series, smooth or straight)

## When to use
Reconstructing a line-chart-shaped graphic from a reference screenshot.
For live-data line charts in a deck, prefer ECharts as elsewhere in the
design system.

## Config schema
See configs/example_line.json.

## Build steps
1. grid + axes from y_axis / x_axis
2. map each series value -> (x evenly spaced, y scaled)
3. geometry.smooth_line if smooth else polyline
4. optional area fill under line; optional dots at vertices
5. legend if multiple series

## Failure checks
- smooth vs straight matches original
- dot radius & stroke match
- area opacity/gradient matches
