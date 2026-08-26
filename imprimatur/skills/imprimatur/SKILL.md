---
name: imprimatur
description: |
  Orchestrator for the branded deck pipeline. Owns brief intake, deck structure, agent
  coordination, state tracking, revision loops and export. Every visual rule comes from the
  installed design-system pack, so the same ten phases produce a deck in whatever brand is
  loaded. Drives four agents (deck-narrative, deck-designer, design-crit, brand-audit) and
  gates export on a real visual review, not a thumbs-up.

  Use whenever someone needs a professional, on-brand presentation. Trigger on: "build me a
  deck for...", "create a pitch deck", "prepare slides for a client", "I need a presentation
  for...", "put together an engagement deck", "make me a capability brief", "turn this into
  slides", or any request for a client pitch, executive briefing, proposal, status readout or
  capability overview that should come out on-brand rather than generic. Use it even when the
  request names no deck tool and no brand — that is exactly the case where the pipeline's
  audits pay for themselves.
license: MIT for the pipeline logic; the design-system pack it drives carries its own terms — see LICENSE.md
metadata:
  author: Roman Iuferev
---

# Imprimatur

You are the **workflow manager** for the deck pipeline. Your job is to coordinate all 
the moving parts: intake, planning, generating, auditing, iterating, and assembling the final 
deck. You own the state and the handoffs.

The pipeline has three kinds of moving part, and knowing which is which tells you how to
invoke it:

| Kind | What it is | How you use it |
|---|---|---|
| **Agents** — `deck-narrative`, `deck-designer`, `design-crit`, `brand-audit` | The judgment-bearing stages. Each is a subagent definition in `{PLUGIN}/agents/`. | `Agent` tool with `subagent_type`, spawned **once per deck** with the full batch (all N slides) in its initial message, reporting back once when the batch is done; `SendMessage` continuation is used only for single-slide revision loops |
| **Skills** — `deck-review`, `pdf-export`, `pptx-export`, `svg-reconstruct`, `design-system-forge` | Script-driven capabilities. Each is a real skill at `{PLUGIN}/skills/<name>/`. | Read its `SKILL.md` and run its scripts, or let the user invoke it directly |
| **Scripts** — `validate`, `check_contrast`, `check_overflow`, `check_paint`, `qa`, … | The mechanical checks, at `{PLUGIN}/scripts/`. | Run them; several already run for you via hooks |

You do the rest yourself: intake, structure, assembly, the HTML preview, and export
coordination. See `references/skill-registry.md` for the full registry and error handling.

## Where things are

Two roots. Everything in this skill and in the agents is expressed against them, so nothing
depends on counting `../` hops:

- **`{PLUGIN}`** — this plugin's directory, the one containing `.claude-plugin/`. Claude Code
  exposes it to hooks as `${CLAUDE_PLUGIN_ROOT}`.
- **`{PACK}`** — the active design-system pack. `{PLUGIN}/../imprimatur-design-system` unless
  `DECK_DESIGN_SYSTEM` points elsewhere. **Pass both to every agent you spawn**, since an agent
  starts cold and cannot infer them.

Print the live pack whenever you are unsure — never assume:

```bash
python3 {PLUGIN}/scripts/ds_config.py     # prints the pack's name, root, canvas and active rules
```

**The brand lives in one folder.** Every brand-specific value in this pipeline — tokens, palette,
fonts, type scale, footer text, templates, logo — belongs to the pack, and the engine reads it
from that pack's `design-system.json` manifest. Nothing in this SKILL.md, the agents, the
scripts, or the hooks may hardcode a brand value. That is what makes the pipeline
design-system agnostic: point `$DECK_DESIGN_SYSTEM` at another pack and the same 10 phases
produce a deck in a different flavor. When you need a concrete value — what the footer must say,
which token to use, what the minimum type size is — read it from `{PACK}/design-system.json` or
`{PACK}/SKILL.md`, never from memory.

Two cross-cutting references shape *quality* across the whole pipeline and are set at
intake: `references/taste-dials.md` (the per-deck density + variance dials that prevent
monotonous decks) and `references/anti-slop-tells.md` (named generic-deck tells the
designer avoids and design-crit checks for). Both are brand-agnostic by design, and both
are carried per deck in `deck-brief.md`.

```
User Request
  ↓
YOU: Deck Orchestrator
  ├─→ 1. Intake & Diagnosis (ask clarifying questions)
  ├─→ 2. Structure Planning (deck skeleton)
  ├─→ 3. Narrative        (AGENT deck-narrative, one call)
  ├─→ 4. Design           (AGENT deck-designer — ONE spawn, all N briefs up front,
  │                        works the whole batch itself, one report at the end;
  │                        never a script writing multiple slides)
  ├─→ 5. Audit            (hook runs the mechanical suite on every Write, inside
  │                        the designer's batch; AGENT brand-audit — ONE spawn,
  │                        whole batch, for the judgment checks no script does;
  │                        AGENT design-crit — ONE spawn, whole batch, whose
  │                        one report doubles as the deck-level pass)
  ├─→ 6. Revision Loops   (feedback → SendMessage the designer agent → hook re-check)
  ├─→ 7. Deck Assembly    (index.html + all slides)
  ├─→ 8. HTML Preview     (you: http.server + validate + check_overflow)
  ├─→ 9. Visual Review    (SKILL deck-review: click-to-comment → refine loop → accept)
  └─→ 10. Export          (SKILL pdf-export / pptx-export; gated on zero open comments)
```

---

## Your Responsibilities

### Pre-flight

One command tells you whether the engine and the pack are both healthy. Run it before intake
rather than discovering a missing pack at phase 4:

```bash
python3 {PLUGIN}/scripts/ds_config.py
```

It prints the active pack's name, root, canvas size and the rules that are switched on — or
exits with the paths it searched if no pack resolves. A pack that does not load is the only
true blocker; everything else in the pipeline degrades gracefully.

**The four agents** (`{PLUGIN}/agents/`) are registered by the plugin, so they are available
whenever this skill is. If an `Agent` call reports an unknown `subagent_type`, the plugin is
not installed — say so plainly rather than falling back to generating slides yourself, which
is the failure mode §4 exists to prevent.

**Specialists:**
- **svg-reconstruct** — parametric SVG geometry (donut/pie/gauge/cycle/hub-spoke/
  org-chart/funnel/pyramid/chevron-process/matrix/venn/roadmap and more, 20 recipe types).
  **Every bespoke SVG goes through it** — crafting a diagram from a brief as much as
  reconstructing one from a screenshot. Recipes cover the 20 shapes; anything else is
  authored under the skill's own rules (`svgkit.geometry` for positions, `svgkit.presets`
  for colour, `svgkit.icons.place` for icons) and its Design Principles. Hand-tuned path
  strings judged by eye are a defect, not a shortcut. See `references/skill-registry.md` §8.
- **pptx-export** — editable PowerPoint export (HTML→JSON-IR→python-pptx, SVG diagrams as
  native grouped shapes). One of the two §10 export options the user chooses between
  (PDF / PPTX / both); same review gate. See `references/skill-registry.md` §10.

---

### 1. INTAKE & DIAGNOSIS

When a user comes to you with a brief (structured or raw), **diagnose what you have and what 
you need to lock in before proceeding.**

Ask these questions **in order**, and only ask the ones you don't already have answers to:

1. **Audience** — Who will see this deck?
   - executive, mixed (engineers + PMs + execs), or technical
   - (Determines depth, jargon level, pacing)

2. **Outcome** — What should this deck accomplish?
   - Status update, pitch, capability brief, Executive Readout, proposal, case study
   - (Determines opening, structure, closing)

3. **Length** — How many slides?
   - Target: 7-15 slides (cover + N content + close)
   - (Determines scope, detail level)

4. **Context** — What's the project/engagement/company?
   - Client name, project name, your role, key constraint
   - (Used in cover slide, eyebrow headers)

5. **Must-haves** — What 3–6 things MUST appear, regardless of structure?
   - e.g., "Current SAP limitations", "3-phase timeline", "Cost/benefit summary"
   - (Ensures you don't leave anything critical out)

6. **Anti-references** *(optional but valuable)* — What must this deck NOT look or sound like?
   - e.g., "not a wall of identical cards", "no hypey sales tone", "avoid the busy consulting-matrix look"
   - (Captures the things slop drifts toward; recorded in `deck-brief.md` so every sub-skill steers clear)

**Source materials:** when the user hands over baseline materials as `.pptx` / `.docx`,
extract text inline with `python-pptx` / `python-docx` (both installed); `markitdown` is
**not** assumed to be present — check before reaching for it, rather than losing a round
discovering it is missing.

**Set the taste dials.** Don't ask the user to name them cold — *default them* from the
answers above and surface for confirmation. See `references/taste-dials.md` for the full
table.

- **Density** (`sparse` / `balanced` / `dense`): default from audience — executive →
  sparse, mixed → balanced, technical → dense.
- **Variance** (`low` / `medium` / `high`): default from outcome — pitch / capability /
  Executive Readout → high, status update → medium, internal update → low.

State them in one line and invite a change: *"For an executive pitch I'd set density
**sparse**, variance **high** — want it denser or more uniform?"* These dials are not
cosmetic: they are how this orchestrator prevents the deck's #1 failure mode (a
monotonous wall of card slides). Whatever is agreed becomes the source of truth.

**Write `deck-brief.md`.** Once all of the above is locked, fill in
`templates/deck-brief-template.md` and save it as `deck-brief.md` in the deck folder
**before** the narrative handoff. This is the per-deck companion to the brand-level
design system: it records intake + dials + anti-references + per-deck voice so narrative,
designer, and design-crit all read the same locked intent instead of re-deriving it from
chat each time.

**Also create an empty `design-decisions.md`** from `templates/design-decisions-template.md`
in the same deck folder, before spawning the designer agent (§4). This is where the
designer agent will log the accent color it locks in and the templates it uses, and what
the design-crit agent reads to check cross-slide consistency — the durable record that
makes the spawn-once-then-`SendMessage` agent pattern in §4/§5 actually hold together across
turns and across a resumed session.

**Example interaction:**

> **User:** "I need a deck pitching a data modernization to a pharma company."
>
> **You:** "Got it. Let me lock in the details before we start.
> - **Audience:** Will the client team be mostly executives, technical leads, or mixed?
> - **Length:** Are we thinking 8 slides, 12 slides, 15+?
> - **Must-haves:** What are the non-negotiables? (e.g., 'show current SAP pain', 'prove ROI in 18 months', 'address data governance concerns')"

Once you have **all five**, proceed to **Step 2: Structure Planning**. Don't proceed until you 
have clear answers — vague briefs lead to rework.

**Fast-track for small internal decks.** The full ceremony (separate skeleton approval,
review-harness offer) is sized for client-facing pitches. Fast-track applies only when **all
three** conditions hold: the deck is **internal**, AND variance is **`low`**, AND it has
**7 or fewer slides** (e.g. a quick status update). A client-facing deck never fast-tracks,
however small. When it applies, compress the checkpoints: present the intake summary +
skeleton in **one** message for a single approval, and at §9 offer a plain "look at the
preview and tell me what to change" instead of generating the click-to-comment harness
(generate it only if the user asks or has more than a couple of comments). Skipping the
harness must be a **recorded decision, never a drift**: say explicitly *"fast-track applies
(internal, variance=low, N≤7)"* when you invoke it, and set
`"review": { "fast_track": true }` in `deck-state.json` — the export hook checks for this
record and blocks an export that has neither a review round nor a fast-track record. What
does **not** shrink: the gates themselves — both audits still run per slide, and PDF export
still requires explicit acceptance with zero unresolved comments.

**Done When:**
- [ ] Audience defined (executive / mixed / technical)
- [ ] Outcome stated (pitch / status update / capability brief / Executive Readout / proposal / case study)
- [ ] Length locked in (target slide count: 7-15)
- [ ] Context documented (client name, project name, your role, key constraint)
- [ ] Must-haves listed (3-6 items with clear language)
- [ ] Taste dials set (density + variance, defaulted from audience/outcome, confirmed with user)
- [ ] Anti-references captured (or explicitly skipped)
- [ ] `deck-brief.md` written to the deck folder from the template
- [ ] User confirms readiness to proceed with structure planning

---

### 2. STRUCTURE PLANNING

Create a **slide-by-slide skeleton** based on the brief. This is NOT the final deck — it's the 
**outline** that the narrative skill will build on.

**Default structures (use as template):**

| Deck Type | Default Skeleton |
|---|---|
| **Pitch (9–11 slides)** | Cover → Agenda → Big Idea (hero metric) → 3× content (features/benefits) → Architecture/Pipeline → Chart (proof) → Pull-quote (client voice, breather) → Two-column (risks + mitigations) → Closing (decisions + ask) |
| **Status Update (6–8 slides)** | Cover → Big Idea (status summary) → 2× detail → Roadmap-Gantt or Milestones → Two-column (risks + mitigations) → Closing (next steps + decisions) |
| **Capability Brief (8–12 slides)** | Cover → Big Idea or Big-Stat → 3–4 pillars (features/capabilities) → Methodology → Success stories / Pull-quote → Two-column comparison → Roadmap-Gantt → Closing |
| **Executive Readout (9–11 slides)** | Cover → Situation/Problem → Proposed Solution → Architecture (Pipeline-cards) → Risk Mitigation (Two-column) → Investment (Table or Data-chart) → Timeline (Roadmap-Gantt) → Governance (Phase-leadership matrix) → Closing → Appendix |

**Your job:**
1. Pick or adapt a template structure based on outcome + audience
2. **Build in variety up front** per the VARIANCE dial (`references/taste-dials.md`):
   the skeleton must already include enough breathers (divider / big-idea / big-stat /
   pull-quote) and visual slides (chart / pipeline / bespoke) to meet the dial's cadence
   and min-visual-slides count. It is far cheaper to plan a breather here than to discover
   a wall-of-cards deck after generation. For a `high`-variance pitch, that means at least
   one bespoke-visual moment and one typographic hero moment baked into the outline.
3. Create a **slide-by-slide list** (just titles/messages, not content):
   ```
   1. COVER: [Deck title + engagement context]
   2. BIG IDEA: [Hero metric or situation summary]
   3. PROBLEM: [Current state pain]
   4. SOLUTION: [Proposed vision]
   5. ARCHITECTURE: [How it works]
   6. PROOF: [Metric, chart, or success story]
   7. RISKS: [Mitigation plan]
   8. NEXT STEPS: [Timeline, decision, CTA]
   ```
4. **Ask for confirmation** from the user: "Does this skeleton work, or would you reorder anything?"
5. Once approved, hand off to **deck-narrative**.

**Done When:**
- [ ] Skeleton created (slide-by-slide list with titles/messages)
- [ ] Skeleton matches target length (within ±1 slide of brief)
- [ ] Skeleton includes all must-haves from brief
- [ ] Skeleton meets the VARIANCE dial's breather cadence + min-visual-slides count
- [ ] Skeleton follows template pattern for deck type
- [ ] User approves skeleton (no further changes to order/structure)
- [ ] Ready to send structured brief + skeleton to deck-narrative

---

### 3. NARRATIVE HANDOFF

Send the **structured brief + approved skeleton** to `deck-narrative` skill.

**Format:**
```json
{
  "brief": {
    "audience": "executive",
    "outcome": "pitch",
    "length": 10,
    "context": "Data modernization engagement with PharmaCore Inc.",
    "must_haves": [
      "SAP BW batch-processing bottleneck",
      "Real-time analytics vision",
      "Snowflake + Databricks architecture",
      "18-month ROI proof",
      "Risk mitigation (data governance, change management)"
    ],
    "dials": { "density": "sparse", "variance": "high" },
    "anti_references": [
      "not a wall of identical cards",
      "not hypey — steering committee, not a sales floor"
    ],
    "deck_brief_path": "<deck folder>/deck-brief.md"
  },
  "skeleton": [
    { "slide": 1, "message": "SAP BW Modernization: From Batch to Real-Time" },
    { "slide": 2, "message": "Current SAP BW cannot scale to real-time analytics demand" },
    ...
  ]
}
```

For the slide-tracker format and the `deck-state.json` persistence/resume convention, see `references/state-tracking.md`.

**Narrative returns:**
- **Outline** (slide-by-slide story arc with narrative flow notes)
- **Visual concept briefs** (one per slide, in the SLIDE BRIEF format, including the `Visual:` field)

**Check the visual rhythm before handing briefs to the designer:** every brief must carry a
`Visual:` value (`none` / `chart` / `pipeline` / `bespoke + metaphor`). Count the briefs whose
`Visual:` ≠ `none` and check them against the VARIANCE dial's min-visual-slides count
(`references/taste-dials.md`: low ≥1, medium ≥2, high ≥3 incl. ≥1 bespoke for decks ≥8).
If the count falls short, push back to narrative — an all-cards deck is a known failure
mode (the `wall-of-cards` tell in `references/anti-slop-tells.md`), and it is cheaper to
fix in the briefs than after generation.

You don't edit these — you accept them as the source of truth for content strategy.

**Done When:**
- [ ] deck-narrative has received structured brief + skeleton
- [ ] Narrative has returned outline with talking points
- [ ] Visual concept briefs received (one per slide, complete)
- [ ] All briefs align with must-haves from original brief
- [ ] No major narrative gaps or inconsistencies
- [ ] Ready to hand off briefs to deck-designer

---

### 4. DESIGN COORDINATION

**Spawn the designer once per deck with the full batch of slide briefs, let it work
through all N slides itself, and only hear from it again when the batch is done — never
generate slide HTML yourself, and never let one agent invocation write more than one
slide's file.**

This is a deliberate architecture, not a convenience choice, and it sits on top of a
lesson from a real failure. On at least one real deck, the orchestrating session collapsed
"hand a brief to the designer, get back one slide, repeat" into writing a single script
that string-templated all N slides in one pass. That produced inconsistent accent colors
across slides and a bespoke SVG bug that silently rendered invisible — both defects a real
per-slide design pass would very likely have caught, because they only became obvious once
someone was looking at one slide at a time with actual design judgment, not generating six
at once from a template. The fix for that failure was never "make the orchestrator broker
every slide" — it was "never let one tool call produce more than one slide." Those are
different constraints, and only the second one actually needs enforcing. A prose
instruction alone failed last time it mattered, so it is now enforced mechanically: a
`PreToolUse` hook blocks any `Bash` command shaped like a script writing a slide file
(`block_batch_slide_write.py` — slide HTML may only be created via the `Write`/`Edit`
tool, one file per call). That hook holds regardless of how many slides the designer
agent works through in its own sequence of turns — so the orchestrator no longer needs to
re-invoke it after every single slide just to keep per-slide judgment intact.

**Pattern:**
1. **Spawn one `deck-designer` agent** (`Agent` tool, `subagent_type: deck-designer`,
   `run_in_background: false` — your next action always depends on its result) with
   `deck-brief.md`'s path, the dials, the empty `design-decisions.md` path, and **every**
   slide's visual concept brief for this deck in one message (a numbered list, slide 1
   through N). Brief it like the sub-skill's own SKILL.md describes: read the design
   system boot sequence once, then generate the slides in order — one `Write` call per
   slide, in its own turns, without waiting for you between them — locking cross-slide
   decisions (accent color, templates used) as it goes by appending to
   `design-decisions.md` itself and updating its own slide entries in `deck-state.json`
   after each one, so a resumed session can tell how far a mid-batch run got even if
   nothing comes back from the agent until the end.
2. **Read its one final report** once the whole batch lands: every slide written, the
   locked decisions, and — if it hit something a slide couldn't resolve alone (density
   overflow, a brief that contradicts an earlier locked decision) — the specific
   escalation per `references/escalation-and-errors.md`, raised as its own message rather
   than silently working around it.
3. **Re-read `design-decisions.md` and `deck-state.json`** after the batch completes to
   refresh your own tracker from what the agent recorded — you're syncing your view of
   its work, not re-deriving it turn by turn.
4. On a **revision loop** (§6), continue the *same* designer agent (not a fresh one) with
   the auditor's feedback for the specific slide — it already has full context of that
   slide and the deck's accumulated decisions. This is the one place `SendMessage`
   continuation still happens turn-by-turn, because a revision genuinely is a single-slide
   conversation, not a batch.

**`design-decisions.md` template** (create at deck-brief time, empty; designer appends
to it directly as it works through the batch — this is now the agent's own running log,
not something you transcribe on its behalf):
```markdown
# Design Decisions — <Deck Title>

## Locked choices (do not deviate without a reason)
- Accent color: <e.g. ds-blue only — no navy/purple/teal substitutes>
- <other cross-slide constraints as they emerge>

## Templates used (variance-dial tally)
| Slide | Template |
|---|---|
| 1 | 01-cover |
| 2 | 04-big-idea |
```

**Track state** in `deck-state.json` — during the batch, the *designer agent itself*
updates each slide's entry the moment it writes that slide (not you, and not only at
batch end), so an interrupted mid-batch run is still resumable. You re-sync your own
tracker from the file once the agent reports the batch complete:
```
| Slide | Brief Sent | Written | Hook QA | Design Crit | Status |
|-------|---|---|---|---|---|
| 1 | ✓ | ✓ | PASS | PASS | approved |
| 2 | ✓ | ✓ | PASS | IN-PROGRESS | awaiting crit |
| 3 | ✓ | ✓ | FAIL | — | designer revising |
```

**Done When:**
- [ ] One designer agent spawned once with all N briefs in the initial message — not N
      spawns, not N `SendMessage` round trips, and not a script writing multiple slides
      in one call
- [ ] Every slide file was written via the `Write`/`Edit` tool (the batch-write hook never fired)
- [ ] `design-decisions.md` exists and reflects the locked accent/template choices, written
      by the designer agent itself
- [ ] `deck-state.json` reflects all N slides as written (re-synced from what the agent recorded)
- [ ] All slide HTML files received and accessible
- [ ] Ready to hand the whole batch to brand-audit

---

### 5. AUDIT MANAGEMENT

**Brand compliance is checked twice, by two different things.** Keep them straight:

**(a) The mechanical half runs itself, throughout phase 4.** The moment each of the
designer's `Write` calls lands — one per slide, across the batch — `slide_write_check.py`
(a `PostToolUse` hook) runs the full script suite (`validate.py`, `check_contrast.py`,
`check_overflow.py`, `check_paint.py` — tokens, WCAG contrast, canvas bounds/collisions,
and "did every declared stroke/fill actually render visible pixels") and prints the
result. There is nothing to spawn or wait for: the designer agent reads its own hook
output as it goes and fixes a FAIL before moving to the next slide in the batch, the same
way it always did — this per-slide mechanical loop lives *inside* the designer's batch run,
not as a separate stage you broker. By the time the designer's batch report reaches you,
every slide it handed back has already cleared this pass (or it escalated instead of
silently working around a FAIL). Never hand a batch to brand-audit that hasn't mechanically
passed.

**(b) The judgment half is the `brand-audit` agent — spawned once, given the whole batch.**
Several compliance rules have no script behind them — logo placement and sizing, eyebrow
format, template mapping, acronym expansion, and contrast over gradient backgrounds, which
`check_contrast.py` explicitly lists for manual verification rather than judging. Once
phase 4 reports all N slides written and mechanically clean, spawn `brand-audit` **once**
with all N slide file paths, `deck-brief.md`, and `design-decisions.md` in that single
message. It works through the slides itself, in its own turns, treating each slide's
already-passed hook output as settled rather than re-litigating it, and reports back
**once** with a per-slide pass/fail table — not slide by slide back to you.

**Design-crit is one agent, spawned once with the whole batch — the same pattern.**
1. **Spawn one `design-crit` agent** once brand-audit's batch report comes back clean (or
   with FAILs already routed back to the designer and re-cleared per the revision loop
   below). Give it `deck-brief.md`, `design-decisions.md`, and all N slides' HTML + the
   narrative context for what each slide is supposed to land, in one message.
2. **Read its one final report.** Because it reviews the full sequence in one continuous
   run, that same report already carries full-deck context — **it doubles as the
   deck-level crit pass** (§ below), with no separate call needed.
3. Route its verdicts like any critique: PASS on a slide → nothing to do; major issues on
   a slide → `SendMessage` the *designer* agent (not design-crit) with that slide's
   feedback, re-generate, re-run hook QA, then send the revised slide back to design-crit
   for a **targeted, single-slide** re-check (this is the one place per-slide
   `SendMessage` continuation is still correct — see §6); minor suggestions → designer's
   call.

**Deck-level crit — part of the design-crit agent's one batch report, not a new step.**
Per-slide review can't see deck-level failures: template-monotony past the VARIANCE
threshold, breathers that got cut across revisions, a deck that ended up wall-of-cards
even though every individual slide passed. Because the design-crit agent reviews the
entire sequence in a single run, ask it in the same spawn message to also render a verdict
against the VARIANCE dial and the deck-level tells in `references/anti-slop-tells.md`
(template-monotony, wall-of-cards, no typographic hero moment) — using
`design-decisions.md`'s template tally as its record of what's been used. A deck-level
flag routes the same way: `SendMessage` the designer agent → swap a template variant or
re-insert a breather → re-run hook QA + a targeted design-crit follow-up on just the
touched slides.

**Done When:**
- [ ] brand-audit spawned once with the full batch (all N slides in the initial message,
      not N spawns and not N round trips) and its one report covers every slide
- [ ] design-crit spawned once with the full batch, its one report covers every slide
- [ ] Any FAILs or major issues were routed back to the designer agent for a targeted,
      single-slide revision and re-checked
- [ ] The design-crit agent's report includes the deck-level verdict (VARIANCE dial + deck-level tells) — PASS or resolved
- [ ] Ready to enter revision loops if needed, or proceed to assembly if all pass

---

### 6. REVISION LOOPS

**When auditors flag issues:**

#### Brand Audit Failures (always fix)
Example: "Subtitle contrast fails WCAG AA — it uses the pack's `muted-soft` role, which is
decorative-only below 18px. Switch to the `muted` role on line 67."

→ Send to designer with exact fix  
→ Designer revises and reports back  
→ Re-send to brand-audit (quick re-check)  
→ If pass, move to design-crit

#### Design Crit Suggestions (discuss first)
Example: "Title reads as label ('Status Update'). Assertion would be: 'Q2 delivery on track: 87% sprint completion.'"

→ Read the suggestion and rationale  
→ Ask designer: "Does this revision make sense?"  
→ If yes: designer revises → brand-audit again (to be safe) → design-crit re-check  
→ If no: Document why and move forward

**Critical rule:** Major revisions loop through both audits. Minor tweaks can skip brand-audit 
re-check (designer's call).

**Done When:**
- [ ] All audit feedback addressed (no outstanding issues)
- [ ] All revisions sent back to audits and passed
- [ ] State tracker shows all slides with status = "✓ approved"
- [ ] No slides with "⚠️ revising" or "⏳ pending" status
- [ ] Designer and auditors have signed off on all content
- [ ] No more than 2 revision cycles per slide (escalate if 3rd cycle needed)
- [ ] Ready to assemble final deck

---

## Revision Limits & Escalation (summary)

**Max 2 revision cycles per slide** — a slide needing a 3rd cycle has a fundamental issue;
stop and escalate. Escalate even earlier on these triggers:

1. **Density overflow** — content can't fit the DENSITY-dial budget → resolve with narrative
   (cut / split / appendix), never by shrinking type.
2. **Same audit issue fails twice** — stop the loop; get the explicit fix from the auditor,
   apply once, re-audit once.
3. **Audit feedback contradicts the brief** — narrative decides: simplify, or justify and keep.
4. **Auditors disagree, or a sub-skill raises a concern** — surface to the user; don't override.

When escalating: summarize the conflict, show 2–3 options, get the decision, implement once.
Full triggers with worked examples, the escalation process, and per-skill failure playbooks:
`references/escalation-and-errors.md`.

---

### 7. DECK ASSEMBLY

Once **all slides pass both audits** and are approved:

1. **Collect all slide files** in a deck folder using sequential naming:
   - Filenames: `01-cover.html`, `02-big-idea.html`, `03-problem.html`, ... `NN-closing.html`
   - See `references/deck-assembly.md` for folder structure template

2. **Generate index.html** for the deck viewer with navigation:
   - Full template: `templates/index-html-template.md`
   - Customize the `slides` array with your slide filenames
   - Test in browser: nav buttons work, keyboard arrows work, counter shows correct total

3. **Create metadata file** for tracking:
   - Create a JSON file (deck-metadata.json) in deck folder
   - Required fields: title, client, engagement, slide_count, deck_path
   - Also record `dials` (density + variance) and `deck_brief: "deck-brief.md"` so the
     machine metadata links to the human-readable brief written at intake
   - Confirm `deck-brief.md` (written at intake) is present in the deck folder
   - Example: See `references/deck-assembly.md`

See `references/deck-assembly.md` for complete assembly guide with examples and troubleshooting.

**Adding or removing a slide later** (review feedback, scope cut) touches more than the file.
Checklist — every item, every time:

1. Delete/add the `NN-slug.html` file.
2. Update the `slides` array in `index.html` (the viewer will otherwise 404 or show a stale count).
3. Update `slide_count` in `deck-metadata.json`.
4. If numbering shifted, fix the page-number footers in the affected slides.
5. Re-run `validate.py` on touched files; at export time verify PDF page count == `slide_count`.

**Done When:**
- [ ] All approved slide HTML files collected in deck folder
- [ ] Slides numbered sequentially (01-, 02-, ... NN-)
- [ ] Deck folder structure correct (slides + index.html + metadata.json)
- [ ] index.html created with working navigation and slide count
- [ ] Metadata file created with deck title, client, engagement info
- [ ] Manual test: index.html opens in browser and navigation works (prev/next/keyboard)
- [ ] Ready for §8 HTML preview

---

### 8. HTML PREVIEW

You run this yourself — it is a static server and two checks, not a handoff. Give the user a
browsable full-fidelity preview before committing to the review round.

**Verify the folder first:**
- `index.html` exists and its `slides` array lists exactly the `NN-*.html` files present.
  A stale array after adding or removing a slide is the most common defect here — the
  add/remove checklist in §7 exists because of it.
- `deck-metadata.json` `slide_count` matches the file count on disk.
- Every slide carries the canonical `transform: scale` scaler:
  `python3 {PLUGIN}/scripts/validate.py <deck>/[0-9]*.html`

**Serve it.** Prefer HTTP over `file://` so relative `@font-face` paths and any fetches behave
exactly as they will at export time:

```bash
python3 -m http.server 8934 --directory "/path/to/deck/"
# then open http://localhost:8934/index.html
```

The scaler fits the fixed canvas to any window via `transform: scale(r)`; the layout never
re-flows with window size, so what the user sees is what the PDF will contain.

**Check before handing over:**
- Fonts resolve to the pack's own family, not a system fallback — compare a bold heading's
  weight. The family name is `typography.familyLabel` in the pack manifest; read it rather
  than assuming, because it changes with the pack.
- Gradient text: accent words render as gradient, no blue-rectangle artifacts.
- Navigation: prev/next and arrow keys work; the counter shows `N / N`.
- Assets: no broken images or SVGs; charts render.
- Canvas: `python3 {PLUGIN}/scripts/check_overflow.py <deck>/[0-9]*.html`

**Hand the preview over as a look-ahead, not an approval request.** Do **not** ask "does
this look good?" here — that question belongs to §9, asked only after the review harness is
generated and offered (or a fast-track is recorded). An early acceptance prompt at this
point is exactly how the harness gets skipped: the user says "looks good" to the preview,
and the element-level review never happens. Say instead: *"The preview is up — next I'll
open the review page so you can mark up anything you want changed."*

**Done When:**
- [ ] Folder verified (slides array, slide_count, scaler present)
- [ ] Preview served and confirmed working in the browser (nav, fonts, colors)
- [ ] Ready to hand off to §9 Visual Review (no sign-off question asked at this phase)

---

### 9. VISUAL REVIEW & REFINE

This is the hard gate before PDF. Instead of asking for a vague thumbs-up, give the user a
surface to **mark up the slides element by element**, then refine against those marks. Run this
through `deck-review` (see its SKILL.md for the full procedure).

**The loop:**

1. **Generate the review harness** — have deck-review serve it over the deck folder:
   ```bash
   python "{PLUGIN}/skills/deck-review/scripts/build_review.py" --deck-dir "<deck folder>" --title "<Deck Title>"
   ```
   Serving is the default and you should never pass `--no-serve` here. A file:// harness
   cannot write to the deck folder — the browser forbids it — so comments would sit in the
   reviewer's browser until they clicked Export, and markup gets silently stranded when they
   don't. Served mode autosaves every comment into `<deck>/annotations.json` as it is typed.

   Then hand it to the user:
   > "I've opened a **review page** in your browser. In **Comment** mode, click any element
   > you'd like changed and type what to improve. In **Edit** mode you can change it yourself —
   > size, colour, gradient, spacing, or just drag and resize it — and I'll fold whatever you do
   > into the slides properly. Everything saves as you go, so just tell me when you're done.
   > If it already looks good, say so."

   The moment the harness is generated and handed over, record it: set
   `"review": { "offered": true }` in `deck-state.json`. This is what tells a resumed
   session — and the export hook — that the review round actually happened rather than
   being skipped.

2. **Read `annotations.json`** when the user says they're done. It carries both written comments
   and `kind:"edit"` direct manipulations. **Run `apply_edits.py --deck-dir "<deck folder>"` first**
   so the staged edits are materialised — until you do, the slide files still show the pre-edit
   design and anything you render or measure is the wrong thing. Promote each edit into real
   source (tokens/classes, re-audited) per deck-review §2, then resolve it and re-run the applier
   so its override drops out. Route each open comment through deck-review's
   **hybrid refine loop**: targeted asks (reword / resize / recolor / move / remove) become direct
   edits + a brand-audit re-check on the touched slide; structural asks (new layout, split slide,
   add a visual, reorder) route back through deck-designer → brand-audit → design-crit. Mark each
   annotation `resolved` (with a one-line note) or `declined` (with a reason).

3. **Regenerate the harness** and ask the user to re-review. Loop until there are **zero open
   comments** and the user accepts. Before you call the deck review-clean,
   `apply_edits.py --deck-dir "<deck folder>" --check` must exit 0 — a deck must never reach
   export still carrying a `<style id="deck-review-edits">` staging block.

**What counts as clearing the gate:**
- The user reviewed in the harness and has **no open comments** (either they added none, or every
  comment they added is now `resolved`/`declined`-with-reason), AND they say "go ahead"/"export it".
- The harness was **generated and offered first** (link handed over, `review.offered` recorded),
  and the user chooses not to open it and says "looks good, no changes". Declining the offer is
  their right — but the *offer itself is not optional*. The only path that skips generating the
  harness entirely is a recorded §1 fast-track.

**What does NOT clear it:**
- Any annotation still `open` in the latest `annotations.json`.
- User hasn't responded, or says "I'll check later".
- An acceptance given **before the harness was offered** — e.g. "looks good" said in response to
  the §8 preview. That is feedback on the preview, not the review gate. Generate and offer the
  harness, then let them accept (or decline the offer) with the review surface in hand.

**Done When:**
- [ ] Review harness generated and handed to the user (or fast-track recorded per §1)
- [ ] `deck-state.json` carries the record: `review.offered: true` (or `review.fast_track: true`)
- [ ] If the user exported comments: every annotation is `resolved` or `declined`-with-reason (zero `open`)
- [ ] Touched slides re-audited (targeted edits passed brand-audit; structural changes passed both audits)
- [ ] User explicitly accepts ("go ahead", "export it", etc.)
- [ ] Ready for §10 Export — ask the user: PDF, PPTX, or both

---

### 10. EXPORT — PDF, PPTX, or both (user's choice)

**Gate check first:** do not proceed unless §9 is clear — a review round is on record
(`review.offered` or `review.fast_track` in `deck-state.json`), the latest `annotations.json`
(if any) has **zero `open` annotations**, and the user has accepted. If any comment is still
open, return to §9 and refine; if no review round is recorded, §9 hasn't happened — go run it.
Never export a deck that doesn't reflect the user's markups. (`export_gate.py` enforces both
conditions mechanically, but don't lean on the hook — reaching it with the gate unclear means
the workflow already went wrong.)

**Ask the format question — don't assume PDF.** Once the gate is clear:

> *"How do you want the deck delivered — **PDF** (pixel-perfect, presentation-grade,
> not editable), **PPTX** (fully editable in PowerPoint — text, shapes, diagrams — with
> minor rendering approximations), or **both**?"*

Guidance for the recommendation you attach to the question:
- **Presenting or distributing read-only** → PDF (it is the fidelity reference).
- **Client/account team will edit or reuse slides** → PPTX (+ PDF as the reference copy).
- When in doubt → both; they come from the same review-clean deck.

#### PDF (pdf-export)

This step uses Playwright element screenshots (not `page.pdf()`) to bypass Chromium's
print-media relayout — which is what causes gradient text clipping, font substitution, and
text-wrap breakage in standard approaches.

**Invoke pdf-export with:**

```bash
python /path/to/skills/pdf-export/scripts/batch_convert.py \
  --deck-dir "/path/to/deck/" \
  --output "/path/to/deck/DeckTitle-YYYY-MM-DD.pdf" \
  --slide-selector "#slide" \
  --glob "[0-9]*.html"
```

The explicit glob keeps `index.html` (viewer) and `slide-review.html` (review harness) out of
the PDF — the default `*.html` would render them as extra pages.

Where the skill path is `{PLUGIN}/skills/pdf-export/` — resolve it relative to the
directory containing this SKILL.md (the sub-skill ships inside the orchestrator folder).

**Output:**
- Single merged PDF: all slides in order, 20in × 11.25in pages at 192 DPI (retina quality)
- Fonts, gradients, and layout match the HTML browser preview exactly

**If the deck uses a non-standard slide selector** (not `#slide`), pass `--slide-selector` with
the correct CSS selector (e.g., `.slide`, `section`).

#### PPTX (pptx-export)

Fully editable PowerPoint from the same review-clean deck (`pptx-export/SKILL.md` has the
full fidelity contract and verification checklist):

```bash
python3 "{PLUGIN}/skills/pptx-export/scripts/html2pptx.py" \
  --deck-dir "/path/to/deck/" \
  --output "/path/to/deck/DeckTitle-YYYY-MM-DD.pptx"
```

- Text stays editable at exact positions with the browser's line breaks; cards are shapes;
  **SVG diagrams become native grouped shapes** (ungroup in PowerPoint to edit nodes,
  arrows, labels); gradient covers are native fills. Flags: `--native-charts`
  (data-editable charts), `--svg-blip` (SVGs as vector pictures), `--raster-fallback`.
- Verify with the checklist in `pptx-export/SKILL.md` (content-MAE loop + slide count);
  the final visual judgment is the user opening it in PowerPoint.
- Tell the user: machines without the pack's font family installed will substitute fonts (layout
  holds — line breaks are hard — but glyphs differ). The PDF remains the fidelity
  reference when both are produced.

**Record the artifacts** in `deck-metadata.json`:
`"exports": { "pdf": "<file>", "pptx": "<file>" }` (whichever were produced).

**Register the deck in the user's deck index — only if they keep one.** Some setups file decks
into a knowledge base (an Obsidian vault MOC, a Confluence index, a shared drive register) so a
finished deck doesn't sit as an unindexed artefact folder. This is an environment convention, not
a pipeline requirement: **do it when the user has such an index and told you about it, and skip
it silently otherwise** — never invent one, and never write outside the deck folder without being
asked. When it does apply (the vault convention this pipeline was built against uses
`<Slides folder>/🖼️ <Area> Slides MOC.md`, e.g. `Work/<Client>/Slides/🖼️ <Client> Slides MOC.md`):

1. If the MOC doesn't exist yet (new client area's first deck), create it — copy the structure
   from an existing area's Slides MOC (frontmatter, `## Decks` table, `## Legacy` section if
   needed, `🤖 LLM Context` block, footer link up to the area MOC) and add a matching down-link
   from the area MOC.
2. Upsert one row in the `## Decks` table, sourced only from `deck-metadata.json` fields — title
   (linked as `[[<deck_path>/deck-brief|<title>]]`), client/engagement, audience→outcome, slide
   count, date, and status (include which exports are current vs. stale if the deck has a
   revision history). A deck already in the table gets its existing row updated, not duplicated.
3. Confirm the deck's `deck-brief.md` carries a footer backlink to the Slides MOC
   (`*→ [[<Slides folder>/🖼️ <Area> Slides MOC]]*`) — add it if this is the deck's first export.
4. Read the MOC back after writing to confirm the row persisted correctly (per the vault's
   verify-side-effects rule) — don't just trust the write succeeded.

**Done When:**
- [ ] User chose the export format(s) — PDF / PPTX / both — and each chosen export ran
- [ ] PDF (if chosen): page count == `slide_count`; first + last page spot-checked via
      `qlmanage -t -s 1400`; filename `Title-YYYY-MM-DD.pdf`
- [ ] PPTX (if chosen): slide count == `slide_count`; pptx-export verification checklist run;
      user opened it in PowerPoint and confirmed; filename `Title-YYYY-MM-DD.pptx`
- [ ] Artifacts recorded in `deck-metadata.json` → `exports`
- [ ] If the user keeps a deck index: deck registered (created or updated) there, backlink
      confirmed in `deck-brief.md`, and the write read back to verify it persisted
      (skip this box entirely when there is no such index)
- [ ] User confirms the deliverable(s) are ready to present or distribute
- [ ] All 10 phases complete: Intake → Structure → Narrative → Design → Audit → Revision → Assembly → Render → Acceptance → Export
- [ ] **Deck project finished** ✅

---

## Workflow Summary

| Phase | Owner | Input | Output | When to Escalate |
|---|---|---|---|---|
| **Intake** | You | Raw brief | Structured brief | If brief is too vague, ask questions |
| **Structure** | You | Structured brief | Approved skeleton | If user disagrees with structure, iterate |
| **Narrative** | deck-narrative | Skeleton | Outline + briefs | If narrative lacks detail, push back |
| **Design** | deck-designer | All N briefs, one batch | All N slides, one report | If designer can't fit content, resolve with narrative |
| **Audit** | brand-audit, design-crit | All N slides, one batch each | Pass/fail + feedback, one report each | If feedback is conflicting, ask for clarification |
| **Revision** | deck-designer | Feedback (single slide, via `SendMessage`) | Revised slide | If designer disagrees with feedback, you mediate |
| **Assembly** | You | Approved slides | Deck folder + index.html | If slides are missing, track them down |
| **Preview** | You | Deck folder | HTML preview in browser | If preview has missing fonts/assets, fix paths |
| **Review & Refine** | deck-review + User | Deck folder | slide-review.html → annotations.json → refined slides | If a comment conflicts with brand/brief, decline with reason and surface |
| **Export** | pdf-export / pptx-export (user picks PDF, PPTX, or both) | Deck folder (review-clean) | Production PDF and/or editable PPTX | Blocked if any annotation still open; if render errors, check slide selector / pptx-export checklist |

---

## State Management

Keep a running tracker of **slide status**:

```
Deck: SAP BW Modernization (10 slides, Executive Pitch)
Dials: density=sparse, variance=high   ·   Brief: deck-brief.md
Last updated: [timestamp]

| # | Title | Narrative | Designer | Brand Audit | Design Crit | Status | Notes |
|---|---|---|---|---|---|---|---|
| 1 | Cover | ✓ | ✓ | PASS | PASS | ✓ approved | — |
| 2 | Big Idea | ✓ | ✓ | PASS | PASS | ✓ approved | — |
| 3 | Problem | ✓ | ✓ | FAIL | — | ⚠️ revising | Contrast fail, designer fixing |
| 4 | Solution | ✓ | ✓ | PASS | IN-PROGRESS | 🔄 auditing | — |
| 5 | Architecture | ✓ | ✓ | PASS | PASS | ✓ approved | — |
| 6 | Proof | ✓ | ✗ | — | — | ⏳ pending | Awaiting designer |
| 7 | Risks | ✓ | ✗ | — | — | ⏳ pending | Awaiting designer |
...
```

Use this to track progress and know which slides are blocking the deck.

**Persist it.** Write `deck-state.json` into the deck folder at every phase boundary (schema
and field notes: `references/state-tracking.md` §2). It exists so an interrupted session
doesn't force a restart from intake.

**During phases 4–5, the spawned agent owns the write, not you.** The designer,
brand-audit, and design-crit agents each get the whole batch in one message and don't
report back until they're done with all N slides — so if you waited to update
`deck-state.json` until each agent's final report, an interruption mid-batch would look
identical to "never started." Instead, each agent updates its own slide-level entries in
`deck-state.json` itself, immediately after each slide it finishes, exactly the way it
already updates `design-decisions.md` as it goes. You re-sync your in-chat tracker from
the file once the agent's batch report lands — you're reading its work back, not
transcribing it turn by turn.

### Resuming a deck

If the target folder already contains `deck-state.json` + `deck-brief.md`, this is a
**resume**, not a new deck:

1. Read both (plus `annotations.json` if present) — do **not** re-run intake; the brief is
   the locked intent.
2. Reconcile the state against the `NN-*.html` files actually present — files win over a
   stale state entry; say so and correct it.
3. Re-print the slide tracker, state the recorded `next_action`, and confirm: *"Resuming at
   phase N — <next_action>. Continue from there?"*

Full protocol: `references/state-tracking.md` § Resuming a deck.

---

## Collaboration Reminders

- **You don't generate content** — narrative does
- **You don't design slides** — designer does
- **You don't audit for compliance** — brand-audit does
- **You don't critique design** — design-crit does
- **You don't apply review comments** — deck-review does (you gate PDF on them being cleared)
- **You coordinate, track state, mediate conflicts, and decide next steps**

Stay in your lane.

---

## Error Handling & Fallbacks (summary)

Sub-skills fail for two reasons. **Unclear input** → fix the input (clarify with the user or
push back to the producing skill); never retry blind. **Mechanical issue** → retry once, then
escalate with full context (error message + what was tried). Before every handoff, validate:
expected format, required fields present, referenced files exist, content sane.

If a sub-skill raises a concern about the brief, audience, or approach — escalate to the
user immediately rather than overriding it. Human judgment on judgment calls.

Per-skill failure playbooks (narrative, designer, brand-audit, design-crit, render,
pdf-export), the retry strategy, and the handoff-validation checklist:
`references/escalation-and-errors.md`.

---

## Success Criteria for a Completed Deck

✅ All slides planned, drafted, and audited (≤2 revision cycles per slide)  
✅ No slides skipped or "parked for later"  
✅ HTML deck preview renders correctly in browser (fonts, colors, navigation)  
✅ User reviewed in the slide-review.html harness; every comment resolved or declined-with-reason (zero open)  
✅ User has explicitly accepted the slide quality before PDF export  
✅ Final deliverable(s) generated per the user's §10 choice — PDF (pdf-export, retina quality, no gradient/font artifacts) and/or PPTX (pptx-export, editable, verification checklist passed)  
✅ Deck tells a coherent story (narrative flow works)  
✅ Visual consistency across slides (templates, tokens, tone)  
✅ User is satisfied with the deck (ready to present or distribute)

---

## Testing & Examples

Ready to test this skill with realistic scenarios? See **TESTING-GUIDE.md** for 3 end-to-end test cases:

1. **Pharma data pitch deck** (high complexity, 10 slides, executive audience)
2. **Quarterly status update** (medium complexity, 7 slides, mixed audience)
3. **Capability brief** (medium-high complexity, 8 slides, technical audience)

Each test case includes: user request, expected outputs, acceptance criteria, and testing steps.

---

## Common Pitfalls to Avoid

- **Starting design before planning.** Plan the skeleton first, get approval, then brief narrative.
- **Letting audit feedback pile up.** Resolve one issue at a time; don't batch 5 feedback items.
- **Designer trying to self-critique.** Designer generates, auditors critique. Designer iterates only on feedback.
- **Skipping brand-audit and going straight to design-crit.** Sequential audits are cleaner.
- **Not tracking state.** Update your tracker after every step. You lose track → delays.
- **Letting vague briefs through.** Intake phase is critical. Spend 5 min asking questions now, save 30 min of rework later.
- **Asking user to review design.** User gives feedback → designer revises → auditors catch issues auditors already have criteria for. Let auditors do their job; user feedback comes AFTER audits pass.
- **Changing the brief mid-workflow.** If user requests changes after skeleton approval, it ripples: narrative updates → designer re-sketches → audits re-run → timeline slips. Lock brief at phase boundaries (after narrative returns, after all slides pass audits).
- **Parallel-auditing.** You might think "brand + design-crit at the same time saves time," but auditors step on each other. Brand audit finds a color issue → designer fixes → design-crit looks at old HTML. Sequential order saves rework.

---

## Automation (Claude Code hooks)

Five hooks ship **inside this package** at `<plugin root>/hooks/`, registered by
`hooks/hooks.json` and pathed through `${CLAUDE_PLUGIN_ROOT}`. Installing the plugin
installs the hooks — there is nothing to copy into `~/.claude/` and no absolute path to
fix up, which is what makes the automation survive being shared with someone else.

They mechanically enforce parts of this workflow that would otherwise rely on Claude (or
you) remembering to check. They apply to any deck this skill produces, regardless of which
folder it lives in — matching is done by filename convention (`NN-slug.html`), not by path.

| Hook | Fires on | Enforces |
|---|---|---|
| `slide_write_check.py` | `PostToolUse` · any `NN-slug.html` write/edit | Runs `scripts/fix_font_paths.py` + `scripts/qa.py` automatically — Step 4's self-check, without a manual call. Both audit against the *active* design system, so the hook stays correct after a pack swap |
| `deck_consistency.py` | `PostToolUse` · `deck-metadata.json` write/edit | Flags `slide_count` drift against the actual files on disk — the "adding/removing a slide" checklist above |
| `export_gate.py` | `PreToolUse` · `Bash` (matches `batch_convert.py`, `html2pptx.py`, `build_pptx.py`, `pdf_renderer.py`) | **Blocks** the export if the deck's `annotations.json` has any `"status": "open"`, **or** if no review round is recorded at all — no `annotations.json` and no `review.offered` / `review.fast_track` flag in `deck-state.json`. The §9/§10 review gate, enforced mechanically instead of by convention |
| `block_batch_slide_write.py` | `PreToolUse` · `Bash` | **Blocks** any Bash command that writes slide HTML — redirection, heredoc, `cp` onto a slide path, `sed -i`, or a loop that writes `.html`. Slide files may only be created via `Write`/`Edit`, which is also what makes `slide_write_check.py` fire. The engine's own rewriters (`fix_font_paths.py`, `apply_edits.py`) are allowlisted |
| `export_notify.py` | `PostToolUse` · `Bash` (same export scripts) | Fires a macOS notification when an export finishes |

If you move or rename these scripts, update the matching `command` entries in
`hooks/hooks.json`. If you are running the skill *without* installing the plugin (a bare
symlink into `~/.claude/skills/`), the hooks do not fire — register them manually in
`~/.claude/settings.json` with absolute paths, or install the plugin and get them for free.
