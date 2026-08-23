# Recipe: Venn Diagram (2-3 overlapping circles)

## When to use
Two or three translucent overlapping circles showing shared/distinct sets.

## Config schema
See configs/example_venn.json.

## Positioning guidance
- 2-circle: offset centers by ~0.8*r horizontally.
- 3-circle: arrange centers in a triangle, each pair overlapping.
- label_x/label_y push labels away from overlap zones.

## Build steps
1. Draw all circles first with fill-opacity so overlaps blend.
2. Draw set labels (positioned in each circle's non-overlapping region).
3. Draw overlap labels at intersection centers.

## Failure checks
- opacity produces visible blended overlap regions
- set labels sit in non-overlap areas
- overlap labels centered in intersections
- circle radii/positions match original overlap proportions
