---
name: design-system-forge
description: |
  Turns a client's brand deck (.pptx/.potx) or brand-guidelines PDF into a working
  design-system pack — manifest, Tailwind token config, slide base, seed templates and an
  off-brand regression fixture — with every token traced to evidence in the source file
  rather than guessed.

  Use whenever a new brand needs to enter the deck pipeline, or whenever someone needs to
  know what a brand's real tokens are. Trigger on: "build a design system for this client",
  "extract the brand from this deck", "here are their brand guidelines", "onboard them into
  the deck pipeline", "what are their actual brand colours", "pull the palette out of this
  PDF", or any time someone is about to hand-author brand tokens. Also when a client sends a
  PPTX or PDF and asks for slides "in their style" — forging the pack first is what makes
  everything downstream on-brand instead of approximate.

  Do NOT use this to build a deck; it produces the pack an orchestrator consumes.
license: MIT for the pipeline logic; the design-system pack it drives carries its own terms — see LICENSE.md
metadata:
  author: Roman Iuferev
---

# Design System Forge

You turn a brand artefact into a **pack**: a self-contained folder of tokens and rules that a
deck pipeline reads to produce on-brand output. The pack is a contract, not a mood board —
downstream engines ask it for `roles.primary` or `typography.allowedWeights` and expect a real
answer.

The bar for "done" is unusual and worth stating up front:

> **A pack must be able to REJECT off-brand work, not just produce on-brand work.**

A folder of pretty colours isn't a design system. A design system knows what violates it. That
is why every pack ships its own off-brand regression fixture, and why the acceptance test is
*templates pass, fixture fails*.

## The one rule that matters most

**Never mint a token without evidence.** Every colour, size, weight and gradient in the pack
must trace back to something actually observed in the source file, with a count and an area
weight. The probe script records this for you; the pack keeps it.

This is not bureaucracy. Brand decks are full of near-duplicates — antialiasing, JPEG artefacts,
a rectangle someone nudged to `#0048FE` by hand. Sampling naively yields hundreds of "brand
colours", and a pack built from those is worse than no pack: it launders noise into a contract
that then vouches for the noise. When you cannot find evidence for a value you think should
exist, say so and leave it out rather than inventing a plausible one.

## Workflow

### 1 · Probe the source

```bash
python3 "{PLUGIN}/skills/design-system-forge/scripts/probe_brand.py" "<brand deck>.pptx" --out evidence.json
python3 "{PLUGIN}/skills/design-system-forge/scripts/probe_brand.py" "<guidelines>.pdf" --out evidence.json --raster
```

The probe dispatches on file type and writes one `evidence.json`: observed colours with area
weights and where they were seen, observed type sizes with their fonts and sample strings,
font families by frequency, and any gradients it can read.

A `.pptx` is the good case and you should say so: it carries a **declared** theme
(`ppt/theme/theme1.xml` — twelve named colours and a major/minor font pair) that the brand's own
designer wrote. That is ground truth, not inference. A PDF has none of it, so everything is
inferred from what the pages happen to contain, and your confidence should be visibly lower.

Read `references/extraction.md` for what each path can and cannot see, and for the traps
(theme-referenced vs literal colours, `potx` masters, PDFs that are one big flattened image).

### 2 · Read the evidence like a designer, not a histogram

Open `evidence.json` and look at the ranked colours before deciding anything. You are looking
for the shape of a system:

- A **structural** colour appears across many pages in large areas (backgrounds, bars, headers).
- An **accent** appears often but small (links, key numbers, one word in a headline).
- A **decorative** colour appears on one or two pages, usually large and unrepeated.
- **Noise** appears once, tiny, and within a hair of a colour you already have.

The same logic applies to type: real ramp steps recur across pages. A size seen twice on one
page is a one-off, not a step.

Say what you concluded in one line, with numbers, before you build anything — *"structural set
is #3F7FD1 (18% of inked area, 22 pages), #1A1A1A (text, 40 pages), #F5F5F5 (surface, 12 pages);
dropping 31 colours below 0.5% as noise."* That sentence is what a human can actually check.

### 3 · Map clusters onto roles — the judgment step

This is the part a script cannot do. The engine asks for semantic **roles**; only the pack knows
which of the brand's colours fills each one. Assign at minimum `primary`, `ink`, `body`, `muted`,
`rule`, `surface`, and an ordered `viz` list for charts.

Two things to get right:

- **`muted` must stay legible.** Pick it against the surface it will sit on and check contrast —
  a brand's "light grey" is very often below 4.5:1 and cannot carry body text. If the brand has
  no legible muted, darken theirs and record that you did, with the ratio. Shipping an
  inaccessible token is a real harm to every deck built afterwards.
- **`viz` order is a decision, not a copy of the palette.** Adjacent series must be
  distinguishable; put the two most separable hues first.

### 4 · Emit the pack

Write your judgment calls into a `decisions.json` first — the id, name, tokens, the role
map, type scale, gradients and which rules apply. `references/pack-contract.md` documents
every field, and carries a complete worked example that is exercised in `evals/`, so it
cannot drift from what the tool accepts. Then:

```bash
python3 "{PLUGIN}/skills/design-system-forge/scripts/emit_pack.py" \
    --evidence evidence.json --decisions decisions.json --out "<packs>/<client>/"
```

`--decisions` is required; `--evidence` is what ties each value back to something observed.
For a pack that was **designed rather than extracted** — a neutral starter, or one typed
from a written brand spec — use `--authored` instead of `--evidence`, so `PROVENANCE.md`
records that honestly instead of implying evidence that does not exist. Add `--force` to
overwrite an existing pack directory.

It writes the skeleton from `assets/skeleton/` filled with your decisions:
`design-system.json`, `tailwind.config.js`, `slide-base.html`, six seed templates,
`off-brand-fixture.html`, the pack's own `SKILL.md`, and `PROVENANCE.md`. Turn a rule
**off** when the brand genuinely has no such constraint, rather than inventing data to
satisfy it — `references/pack-contract.md` lists what data each of the 18 rules needs.

Set `licensing.assetsRedistributable` honestly. Client fonts and logos are almost never
redistributable, and the pack is the natural place to say so.

### 5 · Verify — the acceptance test

```bash
python3 "{PLUGIN}/skills/design-system-forge/scripts/verify_pack.py" \
    --pack "<packs>/<client>/" --orchestrator "{PLUGIN}"
```

**Pass `--orchestrator` explicitly.** Without it the script searches for any installed
`validate.py` and picks one, which on a machine with more than one deck pipeline installed
means the pack gets verified against the wrong engine and still prints ACCEPTED. It now
refuses when the choice is ambiguous, but naming the engine is better than relying on that.

This checks the pack against the contract on its own, then runs that engine's `validate.py`
— the real thing the pack will face in production. Two results must both hold:

- the pack's own seed templates **pass**
- `off-brand-fixture.html` **fails**, and fails on the rules it was built to trip

A fixture that passes means the pack cannot defend itself; go back and find out which rule is
toothless. Report both outcomes with the actual counts. Never report a pack as done on the
strength of the templates alone — that is exactly the half-measure this skill exists to prevent.

## What to hand back

State plainly, in this order: where the pack is, what the probe found (counts, not adjectives),
which judgment calls you made and why, what you could not determine from the source, and the
verification result. The unknowns matter as much as the findings — a pack whose gaps are named
can be finished by a human in ten minutes; one whose gaps are papered over gets discovered three
decks later.

## When the source is thin

Brand artefacts are often worse than they look: a 6-page teaser with two colours, a PDF that is
a single flattened export, a deck that inherited half its styling from a template nobody has.
Say so early and offer the honest options — forge a partial pack and mark the gaps, ask for a
better source (a `.potx`, the brand guidelines, a link to their site), or supplement from the
brand's live site. Do not quietly pad a thin pack with defaults; a pack that claims more than it
knows will be trusted, and that is worse than an obviously incomplete one.
