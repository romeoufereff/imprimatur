# Recipe: Cycle Diagram (circular repeating process)

## When to use
Steps arranged in a circle with curved arrows flowing between them,
showing a repeating loop (e.g., PDCA, continuous improvement).

## Config schema
See configs/example_cycle.json. A node with neither `stops` nor `color` gets
`presets.sequential_stops(i, n)` automatically — real per-node hue variation
(cycle steps are distinct stages, like donut wedges), not a flat fill.

## Build steps
1. Distribute n nodes evenly around the circle (angle = 360*i/n + rotation).
2. Draw curved arrows between consecutive nodes along the ring
   (geometry.text_arc path + arrow marker), with angular padding so
   arrows don't overlap nodes.
3. Draw node circles (gradient/flat), icon above centered label.

## Failure checks
- arrows flow consistently (all clockwise or all counter-clockwise)
- arrowheads point in the flow direction
- nodes evenly spaced; rotation honored
- arrow arcs sit on the ring radius, clear of node circles
- adjacent nodes read as distinguishable hues, not one color repeated
