# Imprimatur

**Author:** Roman Iuferev

A Claude Code plugin that turns a raw brief ("I need a deck pitching X to client Y") into a
presentation-ready PDF or editable PPTX — with brand compliance and design-quality gates built
into the loop instead of left to a human reviewer at the end.

**It is design-system agnostic.** The pipeline holds the *process*; a swappable
`design-system/` folder holds the *brand*. Replace that folder and the same ten phases, the same
audits, and the same gates produce a deck in a completely different flavor. The pack shipped here
is the brand's; see [Swapping the design system](#swapping-the-design-system) to use your own.

This is the orchestrator skill plus 8 required sub-skills and 2 optional specialists
(svg-reconstruct, pptx-export), each a self-contained `SKILL.md`. The orchestrator owns intake,
coordination, state tracking, and the final export gate; it never generates content or pixels
itself.

## Why this exists

A single "write me a deck" prompt to an LLM reliably produces the same failure modes: walls of
identical bullet cards, labels instead of assertive titles, off-brand colors, text that overflows
its container. Splitting the work into narrow roles with hard gates between them (generate →
mechanical audit → design critique → human visual review) catches those failures before they reach
a client-facing PDF.

## Process (10 phases)

```
User brief
  │
  ▼
1. INTAKE & DIAGNOSIS      orchestrator asks audience/outcome/length/context/must-haves,
                            sets taste dials (density + variance), writes deck-brief.md
  ▼
2. STRUCTURE PLANNING      orchestrator drafts a slide-by-slide skeleton, user approves
  ▼
3. NARRATIVE HANDOFF       deck-narrative turns the skeleton into a story arc + one
                            visual concept brief per slide
  ▼
4. DESIGN COORDINATION     deck-designer generates each slide as self-contained HTML
  ▼
5. AUDIT MANAGEMENT        brand-audit (mechanical: tokens, contrast, fonts) →
                            design-crit (principles: hierarchy, narrative, anti-slop)
  ▼
6. REVISION LOOPS          designer fixes flagged issues, re-audits (max 2 cycles/slide,
                            then escalate to user)
  ▼
7. DECK ASSEMBLY           orchestrator collects slides into a deck folder, builds
                            index.html (nav viewer) + deck-metadata.json
  ▼
8. HTML PREVIEW            the orchestrator serves the deck locally for a full-fidelity
                            browser preview (fonts, gradients, nav)
  ▼
9. VISUAL REVIEW & REFINE  deck-review generates a click-to-comment harness; user marks
                            up elements; comments are applied and re-audited until zero
                            open comments and explicit user acceptance
  ▼
10. EXPORT                 user picks PDF, PPTX, or both: pdf-export renders a production PDF via
                            Playwright element screenshots (not page.pdf()); pptx-export builds a
                            fully editable PowerPoint (native text/shapes, SVG diagrams as
                            ungroupable shape groups)
```

Full phase-by-phase detail, revision-limit rules, and error handling live in
[`SKILL.md`](SKILL.md). End-to-end test scenarios live in [`TESTING-GUIDE.md`](TESTING-GUIDE.md).

## Architecture: engine vs. pack

Everything in this package falls on one side of a single line.

| | **Engine** (brand-blind) | **Design-system pack** (brand-specific) |
|---|---|---|
| What | The 10-phase workflow, all sub-skills, all QA scripts, the hooks | Tokens, palette, fonts, logo, footer string, type scale, templates |
| Where | Everywhere *except* `design-system/` | `design-system/` — one folder, nothing outside it |
| Knows about the brand | **Nothing.** It asks the manifest | It *is* the brand |
| Licensed | MIT | Whatever the brand owner says (see [License](#license)) |

The engine never hardcodes a token name, hex, font, footer string, or type size. When a script or
a sub-skill needs one, it reads `design-system/design-system.json` — the contract between the two
halves — via `scripts/ds_config.py`. That single indirection is what makes the swap work, and it
is enforced by convention plus a leak scan (see [Verifying a swap](#verifying-a-swap)).

## Swapping the design system

### The short version

Replace the `design-system/` folder with your own, keeping the same internal structure and a
valid `design-system.json`. Nothing else changes. To keep several packs side by side, leave the
default in place and point an environment variable at the one you want:

```bash
export DECK_DESIGN_SYSTEM=/path/to/acme-design-system
```

Resolution order is `$DECK_DESIGN_SYSTEM`, then the pack shipped beside the plugin
(`{PACK}`). If neither holds a
`design-system.json`, the scripts stop with an actionable error rather than silently falling back
to defaults — a pass against rules nobody declared would be worse than no check at all.

### What a pack must contain

```
your-design-system/
├── design-system.json     ← REQUIRED — the contract (see below)
├── SKILL.md               ← the prose rulebook the designer reads before every slide
├── tailwind.config.js     ← token definitions: 'yourprefix-name': '#RRGGBB'
├── slide-base.html        ← the canonical slide shell: config block, @font-face, footer, scaler
├── templates/*.html       ← the slide template library (this is the real work — see below)
├── fonts/                 ← font files referenced by slide-base.html
├── references/            ← per-template anatomy docs, known issues
├── snippets/  ·  charts/  ← optional: reusable diagram + chart examples
└── gallery.html           ← generated by scripts/build_gallery.py
```

**Be honest about the effort.** Swapping colors and fonts is an afternoon. Templates are the
design system — a pack with no templates gives the designer nothing to copy, and the mechanical
`data-template` check will fail every slide. Two realistic paths:

1. **Derive from an existing pack.** Copy `design-system/`, rename the token prefix everywhere
   (`sed -i '' 's/ds-/acme-/g'` across `templates/*.html`, `slide-base.html`,
   `tailwind.config.js`, `snippets/`, `charts/`), swap the hex values, fonts, logo markup, and
   footer string, then update `design-system.json`. You inherit the whole template library and
   its layout thinking; you own the visual result.
2. **Author your own.** Start from `slide-base.html`, build templates one at a time, and run the
   validators after each. Slower, but the templates end up genuinely yours.

### What `design-system.json` declares

The manifest is the only thing the engine reads to learn your brand. The shipped pack is the worked example; every key is documented inline there with a `$comment`.

| Section | Declares | Consumed by |
|---|---|---|
| `canvas` | Slide dimensions (e.g. 1920×1080) | validators, overflow/contrast checks, gallery |
| `tokens` | Token `prefix`, and the file/dir names inside the pack | validate.py, designer, gallery |
| `typography` | `minFontSizePx` floor, `allowedWeights`, font utility class, family stack + label | validate.py, brand-audit |
| `footer` | `requiredText` (grep marker) and `label` (human string) | validate.py, brand-audit, designer |
| `gradients` | `canonical` gradient strings + `brandHexMarkers` | validate.py gradient-canon check |
| `palette` | `censusSources` — which pack files define the sanctioned hexes | validate.py palette firewall |
| `roles` | **The key abstraction.** Maps semantic roles (`primary`, `accent`, `ink`, `muted`, `rule`, `tint`, `viz`…) onto *your* token names | svgkit presets, PPTX chart colors, gallery chrome |
| `svg` | Font stack, gradient stops, wedge sequence, icon stroke, min sizes for generated SVG | svg-reconstruct/svgkit |
| `pptx` | `fontFamilyByWeight` — installed per-weight family names PowerPoint resolves by | pptx-export |
| `rules` | On/off switches for each mechanical check | validate.py |
| `ruleNotes` | Your own explanation appended to a failure message | validate.py messages |
| `exemptions` | Pack-specific escape hatches (e.g. templates allowed to bleed decoration off-canvas) | check_overflow.py |
| `licensing` | Whether the pack's assets may be redistributed | humans |

`roles` deserves a note: engine code that needs a color asks for a *role*, never a token name.
`ds.color("primary")` looks up `roles.primary` → your token name → its hex in your Tailwind
config. That is why the SVG builder, the PPTX chart styling, and the template gallery all
re-flavor themselves without a line of code changing.

A rule you don't want is simply `false` in `rules` — unknown or absent rules default to off, so a
minimal pack can start with structure checks only and turn the firewall on as the pack matures.

### Verifying a swap

Run these from the skill root after pointing at a new pack. They are the same checks the pipeline
runs on every slide, so a green run means the pack is wired correctly:

```bash
python3 scripts/ds_config.py          # prints the resolved pack, prefix, canvas, active rules
python3 scripts/validate.py           # grep-level checks across the pack's whole template set
python3 scripts/check_contrast.py     # render-level WCAG AA (Playwright)
python3 scripts/check_overflow.py     # render-level canvas bounds (Playwright)
python3 scripts/build_gallery.py      # regenerate the visual catalog, then eyeball it
```

And confirm no brand value leaked back into the engine — this should print nothing:

```bash
grep -rn -i "yourbrand" . --exclude-dir=design-system --exclude-dir=evals
```

## Sub-skills

| Skill | Role |
|---|---|
| [`design-system`](design-system/SKILL.md) | The swappable brand pack — tokens, template library, typography, SVG/chart rules. Not a workflow step; every other skill reads it. |
| [`deck-narrative`](deck-narrative/SKILL.md) | Story strategist — Pyramid/S-curve/SCQA framing, slide-by-slide visual concept briefs |
| [`deck-designer`](deck-designer/SKILL.md) | Generates each slide as self-contained HTML from a brief + the design system |
| [`brand-audit`](brand-audit/SKILL.md) | Mechanical compliance checks (tokens, WCAG contrast, fonts, logo, footer) |
| [`design-crit`](design-crit/SKILL.md) | Principles-based design review (hierarchy, whitespace, assertion-evidence, anti-slop tells) |
| *(HTML preview)* | Orchestrator §8, inline — `http.server` over the deck folder plus `validate.py` and `check_overflow.py` |
| [`deck-review`](deck-review/SKILL.md) | Click-to-comment visual review harness + refine loop — the gate before export |
| [`pdf-export`](pdf-export/SKILL.md) | Renders the final deck to PDF via Playwright element screenshots |
| [`svg-reconstruct`](svg-reconstruct/SKILL.md) | *SVG specialist* — parametric geometry for **every** bespoke SVG: 20 recipe types, plus the rules and Design Principles any one-off diagram is authored under. Never eyeball path data |
| [`pptx-export`](pptx-export/SKILL.md) | *Optional export* — editable PowerPoint via Playwright→JSON-IR→python-pptx; pdf-export stays the fidelity reference |

## Verify

```bash
imprimatur/scripts/validate_all.sh          # everything
imprimatur/scripts/validate_all.sh --fast   # skip the browser-rendered checks
```

Seventeen stages: skill structure, agent frontmatter, the brand firewall, the pack's own
rules, WCAG contrast, canvas bounds, silent paint, the acceptance test, and the gates'
own tests. This replaced four copies of "the acceptance test" that lived in four documents
with three different working directories between them.

## Hooks

Five hooks ship **inside the package** and register automatically when it is installed as a
plugin — `hooks/hooks.json` paths them through `${CLAUDE_PLUGIN_ROOT}`, so there is nothing to
copy into `~/.claude/` and no absolute path to repair on someone else's machine.

| Hook | Fires on | Enforces |
|---|---|---|
| `slide_write_check.py` | `PostToolUse` · any `NN-slug.html` write/edit | Auto-runs `fix_font_paths.py` + `qa.py` on the slide that changed |
| `deck_consistency.py` | `PostToolUse` · `deck-metadata.json` write/edit | Flags `slide_count` drift against the files actually on disk |
| `export_gate.py` | `PreToolUse` · `Bash` (export scripts) | **Blocks** export when review comments are still open, or when no review round is recorded at all |
| `block_batch_slide_write.py` | `PreToolUse` · `Bash` | **Blocks** Bash commands that write slide HTML — one slide per turn, via `Write`/`Edit` only |
| `export_notify.py` | `PostToolUse` · `Bash` (export scripts) | macOS notification when an export finishes |

`hooks/test_export_gate.py` covers the gate's nine allow/block cases; run it after touching the
gate logic.

If you run the skill *without* installing the plugin (a bare symlink into `~/.claude/skills/`),
the hooks do not fire — the skill still works, you just lose the mechanical enforcement.

## Installing

As a plugin (recommended — this is what brings the hooks):

```bash
claude plugin validate /path/to/imprimatur
```

then register the repo as a (local, unpublished) marketplace and install from it —
`/plugin install` always takes `<plugin>@<marketplace>`, never a bare path:

```
/plugin marketplace add /path/to/imprimatur-repo
/plugin install imprimatur@imprimatur
```

As a plain skill instead, symlink `skills/imprimatur` into `~/.claude/skills/` — the skill
folder is self-contained, including its scripts and the design-system pack — but you lose
the four hooks.

## Dependencies

Nothing in this pipeline requires a build step for the LLM-authored parts (narrative, design-crit
are pure reasoning skills). The parts that touch a browser or a file need:

| Purpose | Dependency | Used by |
|---|---|---|
| Slide styling | Tailwind CSS **Play CDN** (inline config per file) | design-system templates, deck-designer output |
| Charts | Apache **ECharts 5** (CDN, SVG renderer) | deck-designer, pack `charts/` |
| Fonts | whatever the pack bundles in `design-system/fonts/` | every generated slide |
| Rendering / screenshots | **Playwright** (Python) + `playwright install chromium` | check_overflow, check_contrast, pdf-export |
| PDF assembly | **Pillow**, **PyPDF2** | pdf-export |
| PPTX assembly | **python-pptx** | pptx-export |
| Local preview server | Python **stdlib** `http.server` | orchestrator §8 preview, deck-review served mode |
| Everything else | Python 3 **stdlib only** | validators, gallery, review harness |

```bash
pip install playwright Pillow PyPDF2 python-pptx
playwright install chromium
```

No Node.js, no npm build, no API keys — Tailwind and ECharts load from public CDNs at render time,
and font/token/logo assets are bundled inside the pack.

## Folder layout

```
<repo>/
├── imprimatur/                      ← the engine. Knows no brand values.
│   ├── .claude-plugin/plugin.json
│   ├── agents/                      ← the four judgment-bearing pipeline stages
│   │   deck-narrative · deck-designer · design-crit · brand-audit
│   ├── skills/
│   │   ├── imprimatur/              ← the orchestrator (you are in its README)
│   │   │   SKILL.md · README.md · TESTING-GUIDE.md
│   │   │   references/ · templates/ · evals/
│   │   ├── design-system-forge/     ← builds a pack from a brand deck or PDF
│   │   ├── deck-review/             ← the §9 visual gate
│   │   ├── pdf-export/  pptx-export/
│   │   └── svg-reconstruct/         ← all bespoke SVG goes through this
│   ├── hooks/                       ← 4 hooks + hooks.json (auto-registered)
│   └── scripts/                     ← ds_config, validate, contrast, overflow,
│                                      paint, qa, font paths, inventory, gallery
└── imprimatur-design-system/        ← THE PACK — everything brand-specific
    design-system.json · tailwind.config.js · slide-base.html
    templates/ · references/templates/ · fonts/ · snippets/ · charts/ · evals/
```

The split is the whole architecture: the engine reads every concrete value from the pack's
`design-system.json`. Point `DECK_DESIGN_SYSTEM` at a different pack and the same ten phases
produce a deck in a different brand.

## Using this pipeline

Trigger the orchestrator with a natural request — "Build me a deck pitching X to client Y" — and
it drives the rest, asking for your input only at intake, structure approval, and the final
visual-review gate. See [`SKILL.md`](SKILL.md) for the full trigger list and
[`TESTING-GUIDE.md`](TESTING-GUIDE.md) for worked examples.

## License

The **engine** — SKILL.md files, agent definitions, Python scripts, hooks, prompts, the
manifest schema — is [MIT-licensed](../../../LICENSE.md): free to use, modify, and
redistribute, with attribution.

The **pack is not**. `imprimatur-design-system/` carries brand colour values, logo
geometry and template content, none of which the MIT licence covers. Its fonts are Source
Sans 3 under the SIL Open Font License and are genuinely redistributable; nothing else in
that folder is. The two travel together in this repository, so the licence boundary is the
folder boundary rather than a repository boundary — read the
[scope note](../../../LICENSE.md) before sharing any of it onward.
