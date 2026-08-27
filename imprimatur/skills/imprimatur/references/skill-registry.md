# Deck Pipeline: Component Registry

Every path here is written against the two roots the orchestrator defines — `{PLUGIN}` (the
directory holding `.claude-plugin/`) and `{PACK}` (the active design-system pack). Nothing in
this registry may carry an absolute path, and nothing may count `../` hops.

The pipeline has three kinds of component and they are invoked differently:

| Kind | Where | How |
|---|---|---|
| **Agent** | `{PLUGIN}/agents/<name>.md` | `Agent` tool, `subagent_type: <name>` — spawned with a batch, continued via `SendMessage` only for single-slide revision loops within that batch. `deck-designer` on decks >10 slides gets a fresh spawn per 4–6-slide chunk rather than one agent for the whole deck — see orchestrator SKILL.md §4 |
| **Skill** | `{PLUGIN}/skills/<name>/SKILL.md` | Read the SKILL.md and run its scripts; the user can also invoke it directly |
| **Script** | `{PLUGIN}/scripts/<name>.py` | Run it; several fire automatically via hooks |

---

## Components by path

### 1. Narrative Strategist
- **Path:** `{PLUGIN}/agents/deck-narrative.md`
- **Input:** 
  - Structured brief (audience, outcome, length, context, must-haves)
  - Approved deck skeleton
- **Output:** 
  - Narrative outline (slide-by-slide story arc)
  - Visual concept briefs (one per slide in SLIDE BRIEF format)
- **Frameworks:** Pyramid Principle, S-curve narrative, SCQA, Assertion-Evidence
- **Role:** Content strategy, technical accuracy, message framing
- **When to invoke:** After orchestrator creates deck structure, before design

---

### 2. Design System (Knowledge Base — the swappable brand pack)
- **Path:** `{PACK}/SKILL.md`
- **Contents:**
  - `slide-base.html` — canonical Tailwind config block, font imports, canvas scaler, footer chrome
  - `design-system.json` — **the engine/brand contract**: token prefix, palette census sources,
    type floors, allowed weights, footer label, canonical gradients, role map, canvas size,
    and which mechanical rules are active. Everything the engine knows about the brand
  - `tailwind.config.js` — all token names and hex values (prefixed per the manifest)
  - `templates/*.html` — the pack's slide templates (copy-and-fill); count and naming vary by
    pack — discovered with `scripts/pack_inventory.py`, never assumed
  - `references/templates/*.md` — anatomy docs, when-to-use, Do/Don't per template, where the
    pack provides them
  - whatever snippets and charts the active pack provides — discovered with
    `scripts/pack_inventory.py`, never assumed by filename
- **Role:** Static knowledge base — **not invoked as a workflow step**; read by designer during generation
- **When to use:** Designer reads this before generating any slide; brand-audit refers to `tailwind.config.js` for token validation

---

### 3. Deck Designer
- **Path:** `{PLUGIN}/agents/deck-designer.md`
- **Input:**
  - Visual concept brief (from narrative)
  - Feedback from auditors (if revision)
- **Output:**
  - HTML slide file (self-contained)
  - Generation report (template, focal point, density, validation)
- **Frameworks:** All 10 design frameworks enforced during generation
- **Role:** HTML generation, template selection, frameworks enforcement
- **When to invoke:** For each slide, receives brief from narrative, iterates based on audit feedback
- **Iteration loop:** Designer → brand-audit → design-crit → [if issues] → designer revises

---

### 4. Brand Audit
- **Path:** `{PLUGIN}/agents/brand-audit.md`
- **Input:** Slide HTML file
- **Output:**
  - Compliance report (pass/fail)
  - Specific violations (with line numbers, evidence, fixes)
- **Checks:** 9 objective criteria
  1. WCAG AA contrast ratios
  2. No raw hex colors (tokens only)
  3. Logo placement & sizing
  4. Footer format
  5. Eyebrow format
  6. Font sizes ≥14px
  7. Font weights (only those in `typography.allowedWeights`)
  8. Template mapping
  9. Acronym expansion
- **Role:** Mechanical compliance checking
- **When to invoke:** After designer generates a slide, before design-crit
- **Verdict:** Pass → move to design-crit; Fail → return to designer with violations

---

### 5. Design Crit
- **Path:** `{PLUGIN}/agents/design-crit.md`
- **Input:**
  - Slide HTML file (post brand-audit pass)
  - Narrative context (what the slide should communicate)
- **Output:**
  - Design critique (observations + suggestions)
  - Framework assessment (10 frameworks reviewed)
  - Approval or feedback for revision
- **Reviews:** 10 design frameworks
  1. Visual Hierarchy — focal point clarity
  2. Typography Hierarchy — size/weight intentionality
  3. Whitespace & Density — ≥30% empty space
  4. Assertion-Evidence — title as complete thought
  5. Composition & Layout — intentional asymmetry
  6. Information Design — chart titles = insights
  7. Cognitive Load — atomic items within the deck's DENSITY dial
  8. Color Distribution — 60-30-10 rule
  9. Accessibility & Plain Language — no jargon
  10. Presentation Narrative — slide role in deck story
- **Role:** Principles-based design review
- **When to invoke:** After brand-audit passes
- **Verdict:** Approved → slide done; Major issues → back to designer; Minor suggestions → designer's call

---

### 6. Design System Forge  ·  SKILL
- **Path:** `{PLUGIN}/skills/design-system-forge/SKILL.md`
- **Input:** a brand deck (`.pptx`/`.potx`) or brand-guidelines PDF
- **Output:** a complete pack — `design-system.json`, `tailwind.config.js`, `slide-base.html`,
  seed templates, `off-brand-fixture.html`, `PROVENANCE.md`
- **Role:** produces the pack the rest of the pipeline consumes. Not part of a deck run —
  invoked when a *new brand* needs to enter the pipeline
- **When to invoke:** before the first deck for a client whose pack does not exist yet
- **Acceptance:** `verify_pack.py` — the pack's templates must pass **and** its off-brand
  fixture must fail. A fixture that passes means a rule has no teeth

> **HTML preview is not a component.** It used to be a `deck-render` sub-skill; it is now
> orchestrator §8 done inline — `python3 -m http.server` over the deck folder, plus
> `validate.py` and `check_overflow.py`. There was never enough there to justify a handoff.

---

### 7. Deck Review
- **Path:** `{PLUGIN}/skills/deck-review/SKILL.md`
- **Generator:** `{PLUGIN}/skills/deck-review/scripts/build_review.py --deck-dir <dir> --out <dir>/slide-review.html`
- **Annotation CLI:** `{PLUGIN}/skills/deck-review/scripts/annotations.py --file <annotations.json> list [--open] [--kind edit|comment]|show|resolve|decline` (notes via stdin — never write ad-hoc scripts for status flips)
- **Edit applier:** `{PLUGIN}/skills/deck-review/scripts/apply_edits.py --deck-dir <dir> [--check|--strip]` — materialises staged Edit-mode patches as one inline `<style id="deck-review-edits">` block per slide; idempotent; writes only `open` edits, so promoting one removes its rule
- **Render/measure:** `{PLUGIN}/skills/deck-review/scripts/render.py <slide> --out … [--crop x,y,w,h] [--zoom N] [--sample-column X]` (WebKit by default — catches Safari-only SVG bugs)
- **Input:**
  - Assembled deck folder (NN-*.html slides)
  - `annotations.json` autosaved by the review harness (comments AND `kind:"edit"` direct manipulations)
  - `design-system.json` `editor` block + the pack's token scales — the only vocabulary Edit mode may author
- **Output:**
  - `slide-review.html` — two-mode review harness (renders each slide in a srcdoc iframe): Comment mode for element-anchored feedback, Edit mode for token-constrained direct manipulation (type/weight/colour/gradient/spacing/radius + drag-move + resize)
  - `edits.json` / `edits.css` — the staged patch set, projected for readability
  - `<style id="deck-review-edits">` blocks in the touched slides (staging only — stripped as each edit is promoted)
  - Refined slides (touched slides re-audited) + updated annotation statuses
- **Role:** Visual element-level review + refinement; the §9 quality gate before PDF
- **When to invoke:** After the §8 HTML preview, before pdf-export
- **Refine loop:** targeted comments → direct edit + brand-audit re-check; structural comments → deck-designer → brand-audit → design-crit
- **Gate:** PDF export blocked until zero `open` annotations + user acceptance. A staged edit counts as open until it has been promoted into real source, so `apply_edits.py --check` must exit 0 before export

---

### 8. SVG Reconstruct
- **Path:** `{PLUGIN}/skills/svg-reconstruct/SKILL.md`
- **Input:**
  - Diagram type (classified from a reference screenshot or a spatial-message brief) — 20 types covered, see the skill's Recipe Index
  - Reference screenshot (optional but preferred — enables the render-diff verify loop)
- **Output:**
  - `configs/<name>.json` — the per-image geometry/content config (reusable, editable)
  - `<name>.svg` — the reconstructed SVG, plus `verify_history.json` and a diff heatmap if a reference screenshot was supplied
- **Role:** Specialist for deck-designer's "Bespoke SVG visuals" step — computes radial/segmented/repeating geometry via `svgkit` (trigonometry) instead of hand-authored path strings, and iterates against a render-vs-reference diff loop (Playwright render + PIL/numpy diff) rather than eyeballing.
- **When to invoke:** Whenever deck-designer's bespoke-SVG path is about to hand-author a donut/pie/gauge/cycle/hub-spoke/org-chart/funnel/pyramid/chevron-process/matrix/venn/roadmap/timeline/flowchart shape, or whenever the user has referenced a screenshot the diagram must match. Not part of the required pre-workflow checklist — most decks never need it — but check for it whenever a slide brief's `Visual:` field is `bespoke` and the metaphor matches one of its 20 recipe types.
- **Hands back to:** deck-designer, which merges the returned SVG fragment into the host template's content area, then continues its own Step 4 self-check and the normal brand-audit / design-crit gates — this skill's output is not exempt from those.

---

### 9. PDF Export
- **Path:** `{PLUGIN}/skills/pdf-export/SKILL.md`
- **Entry point:** `{PLUGIN}/skills/pdf-export/scripts/batch_convert.py --deck-dir <dir> --output <file>.pdf --slide-selector "#slide" --glob "[0-9]*.html"`
- **Input:**
  - Review-clean deck folder (zero `open` annotations + explicit user acceptance — the §9 gate)
  - `deck-metadata.json` (`slide_count` used to verify PDF page count)
- **Output:**
  - Single merged production PDF, `Title-YYYY-MM-DD.pdf`, 20in × 11.25in pages at 192 DPI (retina)
- **Process:** Playwright **element screenshots** of `#slide` in screen media (never `page.pdf()`,
  which forces a print-media relayout that breaks gradient text, font metrics, and wrapping) →
  PNG → Pillow PDF pages → PyPDF2 merge. Local HTTP server from filesystem root resolves
  absolute @font-face paths.
- **Role:** Final production export — the last phase (§10)
- **When to invoke:** Only when §9 is clear; never with open annotations
- **Verdict:** Page count == `slide_count` + first/last page spot-check via `qlmanage` → done;
  failures → `--debug` PNGs, check selector/fonts

---

### 10. PPTX Export (one of the two §10 export options — the user chooses PDF / PPTX / both)
- **Path:** `{PLUGIN}/skills/pptx-export/SKILL.md`
- **Entry point:** `{PLUGIN}/skills/pptx-export/scripts/html2pptx.py --deck-dir <dir> --output <file>.pptx`
- **Input:** Review-clean deck folder (same §9 gate as pdf-export)
- **Output:** Editable 16:9 `.pptx` — text as textboxes at exact positions, cards as shapes,
  SVGs/charts/gradient areas as pictures; per-slide JSON IR kept in `<deck>/.pptx-ir/` for debugging
- **Process:** Playwright DOM walk at native 1920×1080 → inspectable JSON IR → python-pptx
  (6350 EMU/px). `--raster-fallback` = every slide one screenshot picture (pixel-perfect, non-editable).
- **Role:** The "client wants to edit it" export; pdf-export stays the fidelity reference
- **When to invoke:** §10, alongside or instead of pdf-export, when the user asks for PPTX/editable
- **Verdict:** slide count matches + geometry cross-check sub-pixel + user opens it in PowerPoint
  (scripted PowerPoint automation has proved unreliable — see the skill's checklist)

---

## Invocation Pattern (LLM-Agnostic)

When orchestrating these skills, use **relative paths from the orchestrator directory**:

### Path-Based Reference (Most Portable)
```
When you need to invoke [skill name]:
1. Read the skill file: ./[skill-folder]/SKILL.md
2. Follow the instructions in that SKILL.md
3. Complete the task as described
4. Return the output to the orchestrator
```

### Example Invocation Flow
```
ORCHESTRATOR: "Time to develop narrative."
→ LLM reads: {PLUGIN}/agents/deck-narrative.md
→ LLM follows narrative skill instructions
→ LLM receives structured brief + skeleton as input
→ LLM produces: narrative outline + visual concept briefs
→ LLM returns output to ORCHESTRATOR

ORCHESTRATOR: "Time to generate slide 1."
→ LLM reads: {PLUGIN}/agents/deck-designer.md
→ LLM follows designer skill instructions
→ LLM receives visual concept brief as input
→ LLM produces: slide HTML + generation report
→ LLM returns output for audit

ORCHESTRATOR: "Audit this slide for compliance."
→ LLM reads: {PLUGIN}/agents/brand-audit.md
→ LLM follows brand audit instructions
→ LLM receives: slide HTML
→ LLM produces: compliance report (pass/fail + violations)
→ LLM returns verdict to ORCHESTRATOR

(and so on...)
```

---

## Dependency & Sequencing Map

```
┌─ ORCHESTRATOR (intake, planning, state tracking)
│
├─→ deck-narrative (story arc, briefs)
│   ├─ Input: structured brief + skeleton
│   └─ Output: outline + visual concept briefs
│
├─→ deck-designer (for each slide)
│   ├─ Input: visual concept brief + auditor feedback
│   ├─ Output: slide HTML + report
│   │
│   ├─→ brand-audit (check compliance)
│   │   ├─ Input: slide HTML
│   │   ├─ Output: pass/fail + violations
│   │   └─ If FAIL: return violations to designer (loop)
│   │   └─ If PASS: move to next audit
│   │
│   └─→ design-crit (check principles)
│       ├─ Input: slide HTML + narrative context
│       ├─ Output: critique + suggestions
│       └─ If major issues: return to designer (loop)
│       └─ If approved: slide is done
│
├─→ ORCHESTRATOR (assemble deck)
│   ├─ Collect all approved slides
│   ├─ Generate index.html (deck viewer)
│   └─ Create deck metadata
│
├─→ §8 HTML preview (orchestrator, inline)
│
├─→ deck-review (visual review + refine — the gate)
│   ├─ Generate slide-review.html (click-to-comment)
│   ├─ Read annotations.json → refine (targeted | structural) → re-audit
│   └─ Loop until zero open comments + user accepts
│
└─→ pdf-export (export PDF — only when review-clean)
    ├─ Input: deck folder + metadata
    ├─ Output: single PDF file
    └─ Quality checks + report
```

---

## Cross-cutting references (quality, set per deck)

These are not workflow steps — they are shared references read by multiple sub-skills to
keep deck *quality* consistent. The orchestrator sets them at intake and records them in
`deck-brief.md`; narrative, designer, and design-crit all read from the same source.

### taste-dials.md
- **Path:** `./references/taste-dials.md`
- **What:** The per-deck **DENSITY** and **VARIANCE** dials — definitions, audience/outcome
  defaults, and the concrete effect on each sub-skill (density budget, template-repetition
  threshold, min-visual-slides count, breather cadence).
- **Read by:** orchestrator (set at intake), narrative (brief `Density:` + visual spread),
  designer (rhythm check + self-check budget), design-crit (Frameworks 3/7 targets).

### anti-slop-tells.md
- **Path:** `./references/anti-slop-tells.md`
- **What:** A named catalog of generic-deck "tells" that survive brand compliance
  (card-in-card, hero-less, centered-everything, template monotony, gradient overuse,
  decorative-only icons, wall-of-cards). Brand-agnostic only.
- **Read by:** designer (Step-4 pre-flight tells scan), design-crit (anti-slop lens).

### deck-brief.md (per-deck artifact)
- **Template:** `./templates/deck-brief-template.md`
- **Instance:** `<deck folder>/deck-brief.md`, written by the orchestrator at intake.
- **What:** The locked per-deck intent — intake answers + dials + anti-references + voice.
  The human-readable companion to the brand-level `design-system/SKILL.md`;
  `deck-metadata.json` links to it.
- **Read by:** narrative, designer, design-crit (all read it before their first step).

---

## File Structure

```
<repo>/
├── .claude-plugin/marketplace.json   ← local install addressing, not a public listing
├── README.md  INSTALL.md  LICENSE.md
├── imprimatur/                 ← {PLUGIN} — the engine. Knows no brand values.
│   ├── .claude-plugin/plugin.json
│   ├── agents/                 ← the judgment-bearing pipeline stages
│   │   ├── deck-narrative.md · deck-designer.md
│   │   └── design-crit.md    · brand-audit.md
│   ├── skills/
│   │   ├── imprimatur/         ← the orchestrator (YOU ARE IN ITS references/)
│   │   │   ├── SKILL.md · README.md · TESTING-GUIDE.md
│   │   │   ├── references/     ← skill-registry.md (this file), taste-dials.md,
│   │   │   │                     anti-slop-tells.md, design-craft.md,
│   │   │   │                     deck-assembly.md, state-tracking.md,
│   │   │   │                     escalation-and-errors.md
│   │   │   ├── templates/      ← deck-brief, design-decisions, index-html
│   │   │   └── evals/
│   │   ├── design-system-forge/  ← builds a pack from a brand artefact
│   │   ├── deck-review/          ← the §9 visual gate  (+ scripts/)
│   │   ├── pdf-export/           ← §10 PDF             (+ scripts/)
│   │   ├── pptx-export/          ← §10 editable PPTX   (+ scripts/)
│   │   └── svg-reconstruct/      ← all bespoke SVG (+ svgkit/, recipes/, configs/)
│   ├── hooks/                  ← hooks.json + the hook scripts it registers
│   ├── scripts/                ← the engine: ds_config, validate, check_*, qa,
│   │                             fix_font_paths, pack_inventory, build_gallery, _paths
│   └── requirements.txt
│
└── imprimatur-design-system/   ← {PACK} — everything brand-specific
    ├── design-system.json      ← the engine/brand contract
    ├── SKILL.md · slide-base.html · tailwind.config.js · gallery.html
    ├── templates/  references/templates/  fonts/  snippets/  charts/
    └── evals/                  ← off-brand fixture + seeded-violation fixtures
```

Swapping `{PACK}` swaps the brand. `{PLUGIN}` never changes.

---

## Quick Reference

| Need | Read This |
|---|---|
| Overview of pipeline | `./SKILL.md` (orchestrator) |
| Per-deck density + variance dials | `./references/taste-dials.md` |
| Revision limits, escalation triggers, failure playbooks | `./references/escalation-and-errors.md` |
| Generic-deck tells to avoid/flag | `./references/anti-slop-tells.md` |
| Per-deck brief template | `./templates/deck-brief-template.md` |
| How to develop narrative | `{PLUGIN}/agents/deck-narrative.md` (AGENT) |
| Brand values: tokens, gradients, type scale, template index | `{PACK}/SKILL.md` (generated per pack) |
| Craft rules: layout, typography practice, SVG, charts | `./references/design-craft.md` (brand-independent) |
| How to generate slides | `{PLUGIN}/agents/deck-designer.md` |
| How to audit for compliance | `{PLUGIN}/agents/brand-audit.md` |
| How to review for quality | `{PLUGIN}/agents/design-crit.md` |
| How to run the visual click-to-comment review + refine | `{PLUGIN}/skills/deck-review/SKILL.md` |
| How to serve the HTML browser preview | orchestrator `SKILL.md` §8 (inline, no handoff) |
| How to export to PDF | `{PLUGIN}/skills/pdf-export/SKILL.md` |
| How to export an editable PPTX | `{PLUGIN}/skills/pptx-export/SKILL.md` |
| How to reconstruct radial/segmented SVG diagrams | `{PLUGIN}/skills/svg-reconstruct/SKILL.md` |
| How to author or fix a design-system template | see *Optional companion skills* below |
| How to build a pack for a new brand | `{PLUGIN}/skills/design-system-forge/SKILL.md` |
| All paths listed here | this file |

---

## Optional companion skills (not shipped with this package)

Two standalone skills are useful for *growing a design system's template library*, but neither
is part of the pipeline and neither ships here — the pipeline runs fine without them. If they
are installed alongside this package, they live as sibling skills, not as sub-skills; resolve
them by name rather than by a relative path out of this folder.

### deck-extractor
- **Input:** PDF deck, or path to an existing generated HTML slide
- **Output:** design-system-compliant template HTML + reference `.md` doc + routing table entry
- **When to invoke:** Standalone — does not go through the orchestrator pipeline

### template-refiner
- **Input:** Path to one or more template HTML files, with or without a specific issue list
- **Output:** Fixed HTML files + change summary + final screenshot + promotion readiness verdict
- **When to invoke:** Standalone — use after deck-extractor to polish extracted templates, or
  directly on any slide that needs refinement

If neither is available, template work is ordinary editing: copy the closest template, change
it, and run `scripts/validate.py` + `scripts/check_overflow.py` until they pass.
