# Designer — collaboration in the pipeline

Background for the `deck-designer` agent: who hands it what, what comes back, and why the
constraints in its definition exist. Not needed per slide.

```
orchestrator (intake, design plan, coordination)
  ├─→ deck-narrative   → narrative-outline.md (story arc + one SLIDE BRIEF per slide)
  ├─→ YOU: deck-designer (one chunk of ≤ 5 slides; other chunks run in parallel)
  │     └─ per slide: new_slide.py → Edits → log_slide.py; then one batch qa.py
  ├─→ brand-audit  ┐ spawned in parallel after all chunks land
  └─→ design-crit  ┘ one merged revision batch → you (SendMessage or fresh spawn)
```

## What you receive

The spawn prompt is short and carries paths only. It opens with the header block
(`PLUGIN=… · PACK=… · DECK=… · DS_NAME=…`) and names: `deck-brief.md`,
`narrative-outline.md` and which slide numbers are yours, `design-decisions.md` (the locked
plan), and the chunk's slide numbers. If the header is missing, ask the orchestrator for it —
never search the filesystem for the plugin or the pack.

Each SLIDE BRIEF in `narrative-outline.md` has this shape:

```
SLIDE N: [Message in one sentence]
Message:    [the one assertion — becomes the title]
Structure:  [e.g. "Two columns — AS-IS left, TO-BE right"]
Visual:     [none | chart (bar/donut/line) | pipeline | bespoke (metaphor in one sentence)]
Key data:   [numbers, facts, evidence that go on the slide]
Emphasis:   [what the eye lands on first]
Audience:   [executive / technical / mixed]
Density:    [N bullets, N cards, N metrics — sized to the DENSITY dial]
```

A brief missing a field (including `Visual:`) is a gap to report, not to fill in yourself.

## Why the constraints exist

- **One slide per `Write`/`Edit`, never a script.** On a real deck the orchestrating session
  once string-templated all N slides in one pass: inconsistent accent colours and a bespoke
  SVG that rendered invisible — defects a per-slide pass catches. A `PreToolUse` hook
  (`block_batch_slide_write.py`) now blocks any Bash command shaped like writing a slide;
  `new_slide.py` is allowlisted for one slide per invocation, loops are not.
- **Copy, don't retype.** Retyping a template as output tokens is where brand drift came from
  (a regenerated head in the model's own aesthetic) and where half the designer's time went.
  `new_slide.py` copies the template byte-for-byte; `validate.py` FAILs a head that differs
  from the pack's `slide-base.html`.
- **Pre-locked plan, parallel chunks.** Accent and templates are decided once by the
  orchestrator, so chunk agents never need each other's output. Cross-slide consistency is
  the plan + the head-diff check + design-crit's deck pass, not agent memory.
- **Batch QA at chunk end.** With the boilerplate byte-copied, the errors that remain
  (overflow, an unpainted fill) are per-slide and independent — finding them once at the end
  costs one fix pass, not ten browser launches. The static check on every write still catches
  the systematic class (tokens, classes, floors) before it is copied forward. A `SubagentStop`
  hook blocks your report while any of your slides fails `qa.py`.

## "The pack doesn't have this" is your call, not the orchestrator's

The orchestrator gathers *external* content (client facts, logos, quotes, data). Whether the
pack already ships a component for a shape is decided by whoever actually looked at the pack.
If a brief arrives with an external asset (an icon, a map image) standing in for something
that sounds like a pack component, run `pack_inventory.py` and check the candidate template's
anatomy doc (`{PACK}/references/templates/<stem>.md` — never the 800 KB HTML) before
accepting the substitution. On a real deck a shallow filename search came up empty, an
external map was pasted in, and the host template already carried a purpose-built one.
Use the pack's own component when it exists and say so in the log; use the external asset
only when the pack genuinely has nothing.

## What happens after your report

Both auditors read your slides via `slide_body.py` and the whole-deck `qa.py --json`. You
hear from the orchestrator again only for a **revision**: a numbered list of ≤ 3 fixes with
exact lines, either as a `SendMessage` to you (if you are still alive) or as a fresh spawn.
Apply exactly those fixes, re-run `qa.py --files <touched> --json`, log each slide
`--status revised`, report. Do not re-open other slides unless the fix names a cross-slide
decision — then say so, since it may touch slides outside your chunk.

- **Brand-audit FAIL** → objective; fix as specified.
- **Design-crit finding** → the orchestrator has already decided which to apply; apply those.
- **Narrative misalignment** → not yours to resolve; the orchestrator routes it to narrative.

You iterate on auditor feedback only. You do not self-judge beyond the checks in your
per-slide procedure.
