# Recipe: Organizational Chart (hierarchy tree)

## When to use
Top-down hierarchy of boxes connected by orthogonal lines
(reporting structure, taxonomy).

## Config schema
See configs/example_org_chart.json. A node with neither `stops` nor `color`
gets `gradients.auto(id, presets.PRIMARY)` — a real light/dark gradient on ONE
hue, not a rainbow: org boxes are conventionally coded by level/department via
an explicit `color`/`stops`, not auto-varied per box.

## Layout note
- Positions are explicit (x,y). The agent computes them during MEASURE
  to match the original's spacing. No auto-layout.
- parent links drive connector drawing (elbow: down, across, down).

## Build steps
1. Index nodes by id.
2. For each node with a parent, draw an orthogonal connector from parent
   bottom-center to child top-center (down -> horizontal -> down).
3. Draw node rounded-rects (gradient/flat), label (bold) + role (light).

## Failure checks
- connectors are orthogonal with a shared horizontal bus per sibling group
- z-order: connectors behind nodes
- label vs role size hierarchy correct
- levels vertically aligned as in original
