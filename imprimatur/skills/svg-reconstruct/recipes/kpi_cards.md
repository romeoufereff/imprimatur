# Recipe: KPI Card Grid

## When to use
Row or grid of metric cards, each with a big number, a label, an optional
icon, and an optional delta (change indicator).

## Config schema
See configs/example_kpi_cards.json. A card with `stops` given as two
DIFFERENT colors reads as a genuine highlight card; a card with neither
`stops` nor `color` stays plain white — that's the correct restrained default
for a metric grid, not every card needs a color. Never write a highlight
card's `stops` as the same color twice; that's a flat fill, not a gradient —
use a literal flat `color` instead if flat is actually what's wanted.

## Build steps
1. Lay out cards in a grid (cols, gap) starting at origin.
2. Each card: rounded_rect with drop-shadow filter; gradient or flat fill.
3. Icon top-left; value large; label under value; delta top-right.
4. delta color: green if starts with '+', red if '-'.
5. text_color defaults to white on gradient cards, dark on flat/white cards.

## Failure checks
- shadow present and soft (matches original elevation)
- delta color logic matches (+ green / - red)
- number vs label size hierarchy correct
- grid spacing even
