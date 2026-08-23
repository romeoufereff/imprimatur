# Installing Imprimatur

Imprimatur turns a brief into a finished deck — narrative, slide design, brand and design
audits, a visual review round, then PDF or PowerPoint export. What separates it from a template
library is that every stage is checked against a design-system pack, and **nothing exports while
a check is failing**.

One plugin, two folders: the engine and the design-system pack it drives. This repo ships with
**ACME Deck System**, a real 25-template pack built with Claude Design (MIT-safe — no client
brand involved), so the pipeline runs out of the box. Two more ready-made packs live in
`packs/` (Game Studio, Minimalist/Outline) if you want a different flavour without building one.
Building a pack for your own brand is `skills/design-system-forge/`, which ships inside it.

## 1 · Prerequisites

| Requirement | Why |
|---|---|
| `python3` **3.10+** | Two scripts use `str \| None` annotations at runtime; 3.9 fails on import |
| Claude Code | Hosts the plugin and its skills |
| Playwright + Chromium and WebKit | Chromium runs the layout checks and PDF export; WebKit is the default for review renders because it catches SVG and gradient bugs Chromium tolerates |
| ~200 MB disk | Mostly the browser binaries |

```bash
python3 --version   # must report 3.10 or higher
```

## 2 · Install the plugin

Clone the repo. Claude Code's `/plugin install` always takes the form `<plugin>@<marketplace>`
— there is no bare-path install — so first register this repo as a marketplace (the manifest
at `.claude-plugin/marketplace.json` that tells Claude Code where the plugin lives), then
install the plugin from it:

```
/plugin marketplace add /path/to/imprimatur-repo
/plugin install imprimatur@imprimatur
```

You can also point `marketplace add` at the GitHub repo directly (`romeoufereff/imprimatur`)
instead of a local clone.

Or, without the plugin mechanism (you lose the four hooks — the mechanical checks stop firing
automatically, though everything else still works): symlink `imprimatur/skills/imprimatur` into
`~/.claude/skills/`.

The design-system pack installs alongside it, as a sibling folder of the plugin. The engine
finds it there with no configuration — §5 covers pointing it somewhere else.

## 3 · Install the Python toolchain

Claude Code cannot install Python packages for you. From the repository root:

```bash
pip install -r imprimatur/requirements.txt
python3 -m playwright install chromium webkit
```

The browser download is the slow part — a few minutes on a first run. A virtualenv is fine
and recommended. The forge's own dependencies (`python-pptx`, `pdfplumber`) are in that same
file; you need them only if you will build packs from brand artefacts.

## 4 · Verify

One command runs everything:

```bash
imprimatur/scripts/validate_all.sh
```

It checks skill structure, the brand firewall, WCAG contrast, canvas bounds, the pack
acceptance test and the export-gate smoke test. The acceptance test is the one that matters
most, and it has two halves that must **both** hold:

```
  templates PASS : True
  fixture  FAILS : True
ACCEPTED.
```

If the off-brand fixture **passes**, a rule in the pack has no teeth — every deck built on it
will drift with nothing to say so. Fix that before using the pack for real work.

To run the pieces by hand instead:

```bash
cd imprimatur
python3 scripts/validate.py       ../imprimatur-design-system/templates/*.html
python3 scripts/check_contrast.py ../imprimatur-design-system/templates/*.html
python3 scripts/check_overflow.py ../imprimatur-design-system/templates/*.html
python3 skills/design-system-forge/scripts/verify_pack.py \
        --pack ../imprimatur-design-system --orchestrator .
```

Expected, against the shipped ACME pack:

```
All 25 file(s) pass. [ACME Deck System]
All 25 file(s) pass WCAG AA contrast.
All 25 file(s) fit the 1920x1080 canvas.
All 25 file(s) free of element collisions.
  templates PASS : True
  fixture  FAILS : True
ACCEPTED.
```

To try one of the other shipped packs instead, point `DECK_DESIGN_SYSTEM` at it (see §5) — e.g.
`packs/game-studio` or `packs/minimalist`.

## 5 · Point it at your own brand

```bash
python3 imprimatur/skills/design-system-forge/scripts/probe_brand.py "YourCompany_Master.pptx" --out evidence.json
```

A `.pptx` is the good case: it carries a *declared* theme — twelve named colours and a font pair
the brand's own designer chose. That is ground truth, not inference. A PDF has none of it, and
gradients in particular do not survive a PDF export at all. The forge says which values it
inferred and which were declared, and records both in the pack's `PROVENANCE.md`.

Ask Claude to run the forge and it will walk the judgment calls — which colour fills `primary`,
whether the brand's grey is legible enough to carry body text — with you.

Once a pack exists, point the pipeline at it. The durable way is an `env` block in
`~/.claude/settings.json`, because it survives plugin updates:

```json
{ "env": { "DECK_DESIGN_SYSTEM": "/path/to/packs/game-studio" } }
```

Confirm it took effect — every validation run prints the active pack's name, so you will see
`[Game Studio Deck System]` instead of `[ACME Deck System]`.

You can also replace `imprimatur-design-system/` in place, which needs no environment at all
but is overwritten on the next plugin update. `DECK_DESIGN_SYSTEM` is the durable route.

Packs distributed as their own repository usually ship an `INSTALLATION.md` covering this — read
it rather than guessing at the path.

## Troubleshooting

**"No design system found"** — the pipeline needs a pack. Either `imprimatur-design-system/`
is missing from beside the plugin, or `DECK_DESIGN_SYSTEM` points somewhere without a
`design-system.json`. The error lists every path it searched.

**Every slide fails on font URLs** — the pack expects font files it does not have. Set
`checkFontUrlsResolve` to `false` in its `design-system.json` if you are not shipping fonts.

**"pack declares contract 2.0, but this engine implements 1.x"** — pack and pipeline are
different generations. Update the pipeline, or rebuild the pack with the matching forge. The
check exists so a mismatch announces itself rather than surfacing as strange design bugs.

**Playwright or browser errors** — run `python3 -m playwright install chromium webkit` again and
watch for download failures; a corporate proxy often blocks it silently.

**The review page shows stale slides** — it is a snapshot from when the server started. Restart
it after slide edits and hard-refresh the tab.

## Licence

MIT, in full — engine and every pack shipped in this repo alike. See `LICENSE.md`. If you swap
in your own brand pack, that pack carries whatever terms its owner sets; the engine's licence
never changes.
