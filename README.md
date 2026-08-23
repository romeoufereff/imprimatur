# Imprimatur

*Let it be printed.*

A deck pipeline that refuses to ship anything off-brand.

Ask for a deck in plain language and it runs the whole thing: narrative, slide design, brand
and design audits, a visual review round where you can edit slides directly, then PDF or
PowerPoint export. What separates it from a template library is that every stage is checked
against a **design-system pack**, and nothing exports while a check is failing.

## What's in here

| | |
|---|---|
| **`imprimatur/`** | The engine. One orchestrator skill, four agents for the judgment-bearing stages, five capability skills, four hooks, and the mechanical checks. Knows no brand values. |
| **`imprimatur-design-system/`** | **ACME Deck System** — a real 25-template pack (mono steel-blue accent, Barlow / Barlow Condensed, cinema-scale type), built with Claude Design and MIT-safe: no client brand involved. Ships so the engine is installable and runnable out of the box; swap it for your own brand. |
| **`packs/`** | Two more ready-made packs to try or swap in: **Game Studio** (vibrant 5-accent rotation, Archivo / IBM Plex Sans) and **Minimalist / Outline** (warm neutral, single accent reserved for active-state marking only, 1280×720 canvas). |

The delivery flow is agentic. The orchestrator spawns `deck-narrative` for the story arc, then
one `deck-designer` agent continued slide by slide so cross-slide decisions actually hold, with
`brand-audit` and `design-crit` reviewing as it goes. The mechanical checks fire automatically
on every slide write via a `PostToolUse` hook, so compliance is not something anyone has to
remember to run.

Need your own brand? `skills/design-system-forge/` builds a pack from a brand deck or PDF, with
every token traced to evidence in the source rather than guessed.

## Install

See **[INSTALL.md](INSTALL.md)**. Short version: clone the repo, point Claude Code at the
`imprimatur/` plugin (or symlink `imprimatur/skills/imprimatur` as a plain skill), then
`pip install -r imprimatur/requirements.txt` and
`python3 -m playwright install chromium webkit` — the checks measure a real rendered page, so
the browser engines are not optional.

## The idea

A folder of pretty colours is not a design system. A design system knows what violates it.

So every pack ships an off-brand fixture, and the acceptance test has two halves that must
**both** hold: the pack's templates pass, and its off-brand fixture fails. A fixture that
passes means a rule has no teeth, and every deck built on that pack will drift with nothing to
say so.

The engine knows nothing brand-specific. Every colour, size and weight is asked of the active
pack through its manifest — which is why swapping the pack swaps the brand.

## Verify

```bash
imprimatur/scripts/validate_all.sh
```

One command: skill structure, the brand firewall, WCAG contrast, canvas bounds, the pack
acceptance test, and the export-gate smoke test.

## Licence

MIT, in full — engine and every pack shipped in this repo (`imprimatur-design-system/` and
everything under `packs/`) alike. See [LICENSE.md](LICENSE.md). If you swap in your own brand
pack, that pack carries whatever terms its owner sets; the engine's licence never changes.
