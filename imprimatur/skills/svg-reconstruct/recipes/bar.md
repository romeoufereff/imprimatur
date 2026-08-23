# Recipe: Bar Chart (vertical/horizontal, grouped)

## When to use
Rectangular bars comparing categorical values, when the source is a
reference screenshot to match pixel-for-pixel — NOT for live-data charts
in a deck, where design-system's ECharts config
(the pack's own chart example, if it ships one) is the correct tool. Use this recipe only when
reconstructing a bar-shaped graphic from an image (e.g. a client-provided
screenshot that must be replicated exactly, decorative bars inside a
larger bespoke diagram).

## Config schema
See configs/example_bar.json.

## Build steps
1. gridlines + y-axis ticks from y_axis min/max/ticks
2. compute bar width from plot width, count, bar_gap_ratio
3. each bar via geometry.rounded_rect + per-bar linear gradient
4. category labels under/beside bars; value labels at bar tops

## Failure checks
- bars share a consistent baseline
- corner rounding only on the value end (not the baseline) if original does so
- gradient direction matches (usually vertical for vertical bars)
