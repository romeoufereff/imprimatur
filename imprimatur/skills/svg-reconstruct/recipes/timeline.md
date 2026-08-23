# Recipe: Horizontal Timeline

## When to use
Events plotted along a horizontal spine, alternating above/below or on an
explicit side.

## Config schema
See configs/example_timeline.json.

## Build steps
1. horizontal spine from start_x to end_x at axis_y
2. events evenly distributed; alternate side or use explicit "side"
3. node circle on spine; connector to card; date/title/desc text
4. optional icon in node

## Failure checks
- even spacing; alternating sides if original alternates
- connector lengths consistent
