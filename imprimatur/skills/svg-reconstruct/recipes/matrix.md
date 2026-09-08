# Recipe: 2x2 Matrix (quadrant map)

## When to use
Two-axis quadrant grid plotting items by two dimensions
(e.g., impact vs effort, BCG matrix). Four labeled quadrants + points.

## Config schema
See configs/example_matrix.json.

## Coordinate convention
- item.x, item.y in [0,1]. x=0 left, x=1 right. y=0 bottom, y=1 top.
- Builder maps y with (1 - y) so higher y is visually higher.

## Build steps
1. Draw 4 quadrant rounded-rects (2px inset) with fills.
2. Quadrant labels near each quadrant's top area.
3. Plot items as circles at mapped positions; label to the right.
4. x-axis label under center, y-axis label rotated -90 on the left.

## Failure checks
- quadrant order TL,TR,BL,BR matches original placement
- item positions honor the [0,1] normalized convention
- axis labels present and correctly rotated
