---
name: design-system-forge
description: |
  Turn a client's brand deck (.pptx/.potx) or brand-guidelines PDF into a complete, working
  design-system pack — design-system.json, a Tailwind token config, slide-base.html, seed
  templates, and an off-brand regression fixture — with every token backed by evidence from
  the source file rather than guessed. Also handles the other half of a pack's life: AMENDING
  one that already exists on disk in HTML form — re-theming it, migrating its type scale,
  fixing an inaccessible token, toggling a rule, or auditing it for drift between the
  canonical tailwind.config.js and what its templates actually ship.
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

The emitted manifest carries a `motion` block (contract 1.1 — how the brand *moves*: entrance
budget, transition, and which classes are eyebrows / numbers so the engine's choreographer
can read a slide). It is a derived default unless the brand states a motion language — if the
guidelines have one (durations, easing, "no bouncing"), put it in `decisions.json` →
`motion`; if the brand must never animate, `"motion": false`. `references/pack-contract.md`
§ Motion has the fields.

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
toothless. Report both outcomes with the actual counts. Then run `audit_pack.py --pack <pack>`
once: it checks the pack against itself (inline configs vs `tailwind.config.js`, token-name
collisions, raw hexes and sizes outside the token system) — the drift check that `verify_pack.py`
does not do. Never report a pack as done on the
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

## Amending an existing pack

Most of a pack's life happens after it is forged. Tokens get corrected, a scale turns out too
small, a brand refreshes one colour, a new rule needs to bite. This is a different job from
forging: there is no fresh artefact to probe, evidence already lives in the pack itself
(`PROVENANCE.md`, the manifest, the templates as-shipped), and the risk is no longer "wrong
guess" but **drift** — the canonical files say one thing and some of the pack's own consumers
quietly say another.

The same rule from the top of this document still governs: *never mint a token without
evidence.* Here "evidence" usually means the pack's own history (what `PROVENANCE.md` already
says, what `design-system.json.version` implies) rather than a probe, but the discipline is
identical — say what changed and why, in one line with numbers, before touching files.

### 0 · Establish a baseline

Before changing anything, run both checks against the pack as it stands:

```bash
python3 "{PLUGIN}/skills/design-system-forge/scripts/verify_pack.py" --pack "<pack>/"
python3 "{PLUGIN}/skills/design-system-forge/scripts/audit_pack.py" --pack "<pack>/"
```

`verify_pack.py` tells you whether the pack currently meets its own contract.
`audit_pack.py` tells you whether the pack is internally consistent: whether
every template's inline config still matches `tailwind.config.js`, whether any token name
collides across Tailwind categories, whether raw hex values or undersized text have crept into
templates outside the token system. **Run this before you start, not just after** — a pack can
carry pre-existing drift that has nothing to do with your change, and attributing it to your
edit wastes time on both ends.

### 1 · Name the change and its evidence

Say in one line what is changing and why, exactly as the forge workflow does for a fresh probe:
*"raising `muted` from #9A9A9A to #6A6A6A — the shipped value is 2.8:1 on the surface token and
fails AA; darkened until 4.6:1"*, or *"adding a `deep` role for gradient chrome — the brand
refresh deck (`2026-refresh.pptx`) declares one new theme colour, `#0C1E3A`, used on 9 of 14
slides."* If the change is a pure design decision with no new source (a scale bump because
reviewers keep saying slides look sparse, a rule toggle because a brand constraint turned out
not to exist) — say that plainly too. It is still a decision worth a sentence, not silence.

Read `references/amendment-patterns.md` before editing anything nontrivial. It generalises the
recurring ways an HTML pack like this one breaks under a change that looks correct in isolation
— token names colliding across Tailwind categories, a token-only fix that never reaches the
templates that hardcode the old value, flexbox and SVG traps that turn a passing mechanical
check into a slide that still looks wrong. Most costly amendment mistakes are on that list
already; five minutes there is cheaper than finding out from a client review.

### 2 · Change the canonical files first

`design-system.json` and `tailwind.config.js` are the source of truth; `slide-base.html`'s
inline config is a copy of the latter. Change these three before touching a single template.
This ordering exists because of a specific, measured failure mode: a scale can be raised in the
tokens while every template keeps its own hardcoded `text-[Npx]`, so the config technically
says the right thing and nothing downstream changes — see the "token-only change" section of
`references/amendment-patterns.md` for the full story and how large that gap got in practice.

If you are editing the inline `tailwind.config = {…}` block inside an HTML file by hand (rather
than regenerating it), do not anchor a regex replacement on a specific brace pattern —
indentation varies between files and a mismatched anchor deletes the wrong closing brace
silently, taking a whole sibling block with it. Match braces properly, or edit through a real
parse of the block, and diff the `{`/`}` counts before and after as a cheap sanity check.

### 3 · Propagate to every consumer

A pack's consumers are not only `templates/*.html`. Anything a deck designer is told to copy
verbatim from — `charts/`, `snippets/`, worked examples in `references/templates/` — carries the
same tokens and rots the same way if skipped, and usually rots *silently* because nothing
outside `templates/` is gated by default. Grep the whole pack for the old value, not just the
directory you meant to change:

```bash
grep -rn "9A9A9A" "<pack>/" --include='*.html' --include='*.js'
```

Then re-run `audit_pack.py` (§0) — it exists specifically to catch a consumer you forgot, by
comparing every file's inline config and literal hex/size usage against the canonical files
rather than trusting that you found them all by eye.

### 4 · Re-verify, measured not eyeballed

```bash
python3 "{PLUGIN}/skills/design-system-forge/scripts/audit_pack.py" --pack "<pack>/"
python3 "{PLUGIN}/skills/design-system-forge/scripts/verify_pack.py" --pack "<pack>/"
```

`audit_pack.py` should come back clean (or only flag pre-existing drift you are not touching).
`verify_pack.py` must still show templates passing and the fixture failing — an amendment that
weakens a rule until the fixture stops tripping it is a regression even though nothing
"failed." If the change touches geometry (a type-scale raise, a spacing token, anything that
moves text), render before and after and measure the difference — text-box positions, computed
font sizes, pixel deltas — rather than asking whether it "looks right." A scale raise that only
changes tokens can pass every mechanical gate and still leave the majority of templates
visually untouched; the only way to know is to measure what actually rendered.

### 5 · Record the decision

Update `PROVENANCE.md` with the same evidence-and-reasoning line from step 1, bump
`design-system.json`'s `version`, and if the pack keeps a running log of cross-cutting fixes
(a `known-issues.md` or similar), add an entry there when the change fixes something that could
recur — a token collision, a silent-paint trap, a contrast failure. That file is what stops the
next person (including a future you) from rediscovering the same bug by hand. State plainly, as
in forging: where the pack is, what changed, what evidence backed it, and the verify/audit
result — never report an amendment done on the strength of the edit alone.
