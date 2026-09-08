# Recipe: Flowchart / Node-Edge Diagram

## When to use
Boxes/diamonds connected by arrows showing a process or decision flow.

## Config schema
See configs/example_flowchart.json. `edges[].style` is `"elbow"` (default,
90-degree orthogonal routing via geometry.elbow_connector) or `"straight"`.
A node with neither `stops` nor `color` gets `gradients.auto(id, presets.PRIMARY)`
— a real light/dark gradient on ONE hue, not a rainbow: flowchart boxes denote
process steps, not distinct categories, so they stay one consistent hue by
default (set an explicit `color`/`stops` per node for status/type coding).

## Build steps
1. index nodes by id
2. draw edges first (behind nodes): elbow_connector or straight line + arrowhead marker
3. draw node shapes (rounded_rect / rect / diamond)
4. node labels centered; optional icon left of label

## Failure checks
- arrowheads present & correct direction
- edges connect at node borders, not centers
- z-order: edges under nodes
- elbow vs straight matches the reference — this is the single most common
  piece of feedback on hand-drawn connectors (curved beziers used where the
  original is 90-degree orthogonal, or vice versa)
