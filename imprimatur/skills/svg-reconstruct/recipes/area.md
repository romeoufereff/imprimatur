# Recipe: Area Chart (filled line, single or stacked)

## When to use
Line chart(s) with the region below filled, emphasizing volume/magnitude
over time. Use `line` recipe if fills are absent.

## Config schema
See configs/example_area.json.

## Build steps
1. Gridlines + y ticks; x labels under plot.
2. For each series: map points to plot coords.
3. Fill path: line path + down to baseline + back to start, closed,
   filled with a vertical gradient (color at 0.55 -> 0.05 opacity).
4. Stroke the line on top of the fill.

## Stacking note
- For stacked areas, the agent supplies cumulative points per series in
  the config (bottom series first). Builder draws back-to-front.

## Failure checks
- fill gradient fades to transparent at the baseline
- smooth vs straight matches original
- line stroke sits crisply on top of fill
- multiple series layered in correct order
