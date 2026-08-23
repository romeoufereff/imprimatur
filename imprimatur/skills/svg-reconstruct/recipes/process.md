# Recipe: Process Chart (horizontal chevron/arrow steps)

## When to use
Sequential left-to-right steps where each step is a chevron/arrow that
notches into the next. Shows a directional workflow.

## Config schema
See configs/example_process.json. A step with neither `stops` nor `color` gets
`presets.sequential_stops(i, n)` automatically — real hue variation per step,
not a flat fill. Set `stops` explicitly only to match a reference's exact colors.

## Build steps
1. Each step is a polygon: left flat edge (or notched-in for steps>0),
   right pointed edge (chevron apex). Uses step_w, step_h, notch.
2. Advance x by (step_w - notch + gap) so chevrons interlock.
3. Icon above label, both centered in the step body.
4. Fill via gradient (explicit stops, flat `color`, or the sequential default).

## Failure checks
- chevrons interlock (right point fits into next left notch)
- first step has flat left edge (no incoming notch) if original does
- icon/label centered on the step body, not the point
- direction of the arrow (left-to-right) correct
