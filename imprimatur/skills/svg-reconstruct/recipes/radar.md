# Recipe: Radar / Spider Chart

## When to use
Multi-axis comparison where each axis radiates from a center; series are
drawn as closed polygons across the axes.

## Config schema
See configs/example_radar.json.

## Build steps
1. Draw concentric ring polygons (rings) as scale guides.
2. Draw one spoke per axis to radius; place axis label just beyond radius.
3. For each series: compute vertex per axis (radius*value/max at
   angle 360*i/n), draw closed polygon with translucent fill + stroke.

## Failure checks
- axis count and order match; labels positioned outside the outer ring
- rings evenly spaced
- series polygons translucent so overlaps read
- values scale so value=max touches the outer ring
