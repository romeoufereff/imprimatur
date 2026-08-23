# Recipe: Stacked Bar Chart

## When to use
Bars where each category is subdivided into stacked segments summing to
the total. Shows composition across categories.

## Config schema
See configs/example_stacked_bar.json.

## Segment order note
- segments[] is bottom-to-top. Preserve original stacking order exactly.

## Build steps
1. Compute per-category totals; ymax = max*1.1 unless `max` given.
2. For each category, stack segments bottom-to-top (rects, shared width).
3. Category labels under bars; legend swatches above plot.

## Failure checks
- segments stack without gaps; totals correct
- legend order matches stack order
- consistent bar width and even spacing
- optional corner rounding only on the topmost segment if original does so
