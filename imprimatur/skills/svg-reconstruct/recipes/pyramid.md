# Recipe: Pyramid Chart (hierarchical levels, apex to base)

## When to use
Triangular stack of horizontal bands, narrow apex widening to base.
Represents hierarchy, maturity levels, or proportional foundations.

## Config schema
See configs/example_pyramid.json. A level with neither `stops` nor `color` gets
`presets.sequential_stops(i, n)` automatically — real hue variation per level,
not a flat fill. Set `stops` explicitly only to match a reference's exact colors.

## Build steps
1. For level i of n: w_top interpolates apex_width->base_width at i/n,
   w_bot at (i+1)/n. Each band is a trapezoid polygon centered on center_x.
2. Fill via linear gradient (explicit stops, or the sequential default).
3. Center label in each band.

## Failure checks
- apex (top band) is the narrowest; base the widest
- band widths increase monotonically
- gradient vs flat matches the reference; don't fake a flat fill as a
  two-identical-stop gradient — write it as a literal flat `color` instead
- gap between bands consistent
