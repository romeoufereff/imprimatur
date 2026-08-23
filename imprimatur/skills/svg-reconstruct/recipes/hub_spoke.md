# Recipe: Hub & Spoke (central node + radiating nodes)

## When to use
One central concept connected by straight lines to several surrounding
nodes. Shows a core with related components (distinct from cycle: no flow
arrows, lines go to center not around).

## Config schema
See configs/example_hub_spoke.json. A spoke with neither `stops` nor `color`
gets `presets.sequential_stops(i, n)` automatically (spokes denote distinct
categories around the hub, like donut wedges — hue variety is the right
default). The hub's `gradient` is optional too — omitting it defaults to an
accent→deep radial, never a flat single-color hub.

## Build steps
1. Draw connector lines from center to each spoke position first (behind).
2. Draw hub circle (radial gradient) with centered label.
3. Distribute spokes evenly (360*i/n + rotation); draw each as a circle
   with icon above centered label.

## Failure checks
- lines drawn behind all nodes (z-order)
- hub uses radial gradient with off-center focal for depth (two DIFFERENT
  colors — never the same role repeated) and a soft drop-shadow lifting it
  above the ring
- spokes evenly distributed; rotation honored
- adjacent spokes read as distinguishable hues, not one color repeated
- distinguish from cycle: NO arrows, lines radiate to center
