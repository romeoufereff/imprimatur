# Deck Pipeline: End-to-End Testing Guide

**Status:** Ready to test  
**Date:** 2026-09-02  
**Test Cases:** 3 acceptance scenarios (pharma pitch, quarterly status, capability brief) + 1 performance scenario  

---


## Running the evals

Scripted graders, all wired into `scripts/validate_all.sh`:

```bash
scripts/run_evals.py audit                     # the pack's seeded-violation fixtures
scripts/run_evals.py setup 1 /tmp/eval-1       # stage a stage-eval's working folder
scripts/run_evals.py designer /tmp/eval-1      # grade what came back
```

See `evals/README.md` for what each tier grades and what it deliberately does not.

## Overview

We have 8 required sub-skills (plus the optional svg-reconstruct and pptx-export
specialists) working together to create complete decks. This guide walks you through testing the full 10-phase pipeline with realistic scenarios. The scenarios below use the pack that ships in this repository; running them against a different pack (via `DECK_DESIGN_SYSTEM`) is itself a useful test — the workflow, gates and outputs should be identical, only the flavor should change.

---

## Two tiers of tests

**Stage evals (run these first, and after any sub-skill change).** `evals/evals.json` ids 1–6:
four single-slide designer runs (two-column pairing, dense chart, bespoke-rings delegation to
svg-reconstruct, big-stat breather), one brand-audit run against two seeded-violation
fixtures (`evals/stage-brand-audit/`, ground truth in `seeded-violations.json` — score
recall 10/10 + zero false positives), and one narrative run against a fixed 9-slide skeleton
(`evals/stage-narrative/skeleton.json` — score brief completeness + visual-rhythm floor).
They're cheap, objective, and mostly script-gradable (`qa.py` exit codes, manifest matching,
field presence). The three full-deck scenarios below are the **acceptance tier** — run them
before declaring a pipeline-wide change done, not for every iteration.

## Test Cases (acceptance tier)

### Test Case 1: Pharma Data Pitch Deck (HIGH COMPLEXITY)

**Scenario:** PharmaCore Inc. — €2M data modernization engagement

**User Request:**
> "I need to pitch a data modernization engagement to PharmaCore Inc., a large pharma company 
> currently using legacy SAP BW. We're proposing a migration to Snowflake + Databricks for 
> real-time analytics. Audience is mostly executives (C-suite + steering committee). We want a 
> 10-slide pitch that covers: current pain, proposed vision, architecture, risk mitigation, 
> investment, timeline, and call-to-action. Make it strong — this is a €2M engagement."

**Expected Output:**
- 10-slide deck in the active design system
- All slides pass brand audit + design crit
- PDF exports cleanly
- Narrative follows Pyramid Principle (conclusion first, support follows)

**Acceptance Criteria:**
- ✅ All 10 slides generated
- ✅ Brand audit: 0 violations across all slides
- ✅ Design crit: All slides approved (no major issues)
- ✅ PDF file exists and renders correctly
- ✅ Slide sequence tells cohesive story
- ✅ Designer iterates only on auditor feedback (not self-judging)

**How to Test:**
1. Copy this user request
2. Invoke: `./imprimatur/SKILL.md`
3. Follow orchestrator through the full workflow
4. Check outputs at each stage (narrative briefs, slides, audit reports, PDF)
5. Review: Do all acceptance criteria pass?

---

### Test Case 2: Quarterly Status Update (MEDIUM COMPLEXITY)

**Scenario:** Internal Q2 project update for mixed audience

**User Request:**
> "We need a quarterly status update for Q2 2026 on our internal data platform modernization 
> project. Audience is mixed: data engineers, platform architects, and a few business 
> stakeholders. Target 7 slides. Must include: status summary (on track), what was delivered 
> this quarter (3 key features), what's in progress, risks (one major: data governance 
> complexity), and next quarter roadmap. Tone should be professional but informal — this is 
> internal."

**Expected Output:**
- 7-slide internal update deck
- Status headlines are assertive (metrics-driven, not labels)
- All audits pass
- PDF ready to email

**Acceptance Criteria:**
- ✅ All 7 slides generated
- ✅ Status updates are assertions, not labels
  - ❌ "Status Update" 
  - ✅ "Q2 delivery on track: 87% sprint completion"
- ✅ Charts/metrics use insight titles
  - ❌ "Monthly Ingestion Rates"
  - ✅ "Data ingestion grew 3x YoY, driven by real-time pipeline"
- ✅ Brand and design audits pass
- ✅ PDF is readable and professional

**How to Test:**
1. Copy this user request
2. Invoke orchestrator
3. Walk through the full workflow
4. Verify: Is every slide title an assertion, not a label?
5. Verify: Do charts communicate insight, not just data?

---

### Test Case 3: AI/ML Capability Brief (MEDIUM-HIGH COMPLEXITY)

**Scenario:** Presales positioning for a new service offering

**User Request:**
> "We are launching a new AI/ML platform service. We need a capability brief to market this 
> to clients in pharma and manufacturing. Executive audience. 8 slides. Must position our 3 
> core capabilities: model development, MLOps automation, and business intelligence integration. 
> Include competitive positioning, methodology, customer success stories (2), and call-to-action 
> for a discovery call. This is a presales deck — make it compelling."

**Expected Output:**
- 8-slide presales capability brief
- Clear positioning (what, why different)
- Success stories with ROI metrics
- All audits pass
- PDF polished for client distribution

**Acceptance Criteria:**
- ✅ All 8 slides completed
- ✅ Capability positioning is crystal clear
- ✅ Success stories include metrics (% gains, timelines, $ savings)
- ✅ Design hierarchy supports presales narrative (confidence, not overwhelm)
- ✅ Brand and design audits pass
- ✅ PDF is client-ready

**How to Test:**
1. Copy this user request
2. Invoke orchestrator
3. Check narrative: Does it explain what the offering does and why it's different?
4. Check success stories: Are there concrete metrics?
5. Check design: Does layout feel confidence-building?

---

### Performance Scenario: 7-slide capability brief (token & speed targets)

**Scenario:** run Test Case 2's request (7 slides, mixed audience, internal) end to end,
with sources attached if you have any, and measure the transcripts afterwards. This is the
regression check for the token-and-speed plan; quality gates are unchanged, so every
acceptance criterion above still applies on top of the numbers below.

**Measure with:**

```bash
python3 scripts/telemetry/session_stats.py <session-id-or-jsonl>
```

It prints, per agent: kind, turns, output tokens, cache-read, ctx peak, minutes, image
reads, tool results > 100 KB, `hook_visible`, and per-slide cycle time (time between
consecutive `new_slide.py` calls). Baseline and post-change numbers live in
`evals/perf-baseline.json`.

**Acceptance criteria (all must hold):**

- ✅ **Designer ≤ 6 tool turns per slide** (`new_slide.py` → 2–6 `Edit`s → `log_slide.py`),
  measured per chunk agent
- ✅ **Context peak ≤ 150 K tokens for every agent** (each designer chunk, brand-audit,
  design-crit, narrative); designer context after boot, before slide 1, ≤ 35 K
- ✅ **`hook_visible == true`**: a `STATIC PASS` / `STATIC FAIL` line follows every slide
  `Write`/`Edit` in the designer transcript
- ✅ **Exactly one `qa.py` batch run per designer chunk** (plus re-runs on touched files
  only); zero `fix_font_paths.py` calls; zero `validate.py` / `check_*.py` calls by hand;
  brand-audit runs `qa.py --deck-dir --json` exactly once
- ✅ **No `Read` of any `templates/*.html`** in any transcript; no `Read` of a PDF/DOCX/VTT
  in the orchestrator transcript (an `Explore` subagent wrote `Input/source-notes.md`)
- ✅ **No tool result > 100 KB** in any transcript
- ✅ **PNG reads ≤ number of bespoke/chart/pipeline slides + FAIL retries**
- ✅ **Zero filesystem searches for the plugin** (`find … plugin`, `ls ~/.claude/plugins…`)
  in any agent transcript — every spawn prompt opened with the header block
- ✅ **All designer chunks spawned in the same turn**; brand-audit and design-crit spawned
  in the same turn
- ✅ **Review-ready in ≤ 25 min of pipeline time** (narrative start → both audits passed and
  deck assembled; the user's own review time excluded)
- ✅ `design-decisions.md` ≤ 4 KB at the end; one designer revision spawn at most for two
  seeded audit findings, one `qa.py` re-check, no second brand-audit / design-crit spawn

**Red flags:** a designer transcript with prose reports between slides · a `qa.py` call
between slides · an orchestrator screenshot of a slide · a spawn prompt over 3 KB or
containing pasted HTML · `design-decisions.md` with paragraphs in it.

---

## Testing Workflow (Per Test Case)

```
┌─ START: Invoke orchestrator with test case user request
│
├─ Step 1: Orchestrator INTAKE
│  └─ Does it ask clarifying questions? (if brief is incomplete)
│  └─ Does it create a structured brief?
│
├─ Step 2: Orchestrator STRUCTURE PLANNING
│  └─ Does it propose a deck skeleton?
│  └─ Does it ask for user confirmation?
│
├─ Step 3: Invoke deck-narrative
│  └─ Does the spawn prompt open with the header block and carry paths only?
│  └─ Does the agent write narrative-outline.md itself (outline + one SLIDE BRIEF per slide)?
│  └─ Are briefs complete (message, structure, visual, key data, emphasis, audience, density)?
│
├─ Step 4a: Orchestrator DESIGN PLAN
│  └─ Does it lock template + accent per slide into design-decisions.md before any designer?
│  └─ Does plan_check.py PASS before the spawn? Are stale NN-*.html archived?
│
├─ Step 4b: Invoke deck-designer — one agent per ≤ 5-slide chunk, ALL in the same turn
│  └─ Per slide: new_slide.py → 2–6 Edits → log_slide.py? No Read of a template .html?
│  └─ Is a STATIC PASS/FAIL line visible after every slide write, and a FAIL fixed before
│     the next slide? No qa.py between slides?
│  └─ One qa.py --files … --json per chunk at the end; stop gate blocks a failing chunk?
│  └─ Report = log_slide.py --summary + escalations (no per-slide prose)?
│  └─ Orchestrator verified from files (--summary + state-vs-disk + whole-deck qa.py)?
│
├─ Step 5: Invoke brand-audit AND design-crit in the same turn (parallel, read-only)
│  └─ brand-audit: one qa.py --deck-dir --json run, then the judgment rows (logo, eyebrow,
│     acronyms, gradient contrast) + any named content check; one table ≤ 40 lines?
│  └─ design-crit: slide_body.py reads, ≤ 3 lines per slide, deck-level verdict from
│     plan_check.py + named tells; no "what works" prose?
│
├─ Step 6: Orchestrator REVISION — one merged batch
│  └─ Brand FAILs + accepted crit findings routed as one fix list (≤ 3 fixes per spawn)?
│  └─ Re-checks script-only (qa.py --files) unless a judgment finding's fix changed layout?
│  └─ No second brand-audit / design-crit spawn; ≤ 2 rounds?
│
├─ Step 7: Orchestrator ASSEMBLY
│  └─ Are all slides approved in deck-state.json?
│  └─ assemble_deck.py wrote index.html + deck-metadata.json (not a designer, not by hand)?
│
├─ Step 8: HTML preview (orchestrator serves it inline)
│  └─ One whole-deck qa.py --json + http.server; URL handed over with the summary line?
│  └─ No orchestrator screenshots of slides; no sign-off question asked here?
│
├─ Step 9: Invoke deck-review (visual review & refine — the gate)
│  └─ Does it generate the click-to-comment harness (build_review.py --serve)?
│  └─ Are annotations refined (targeted → direct edit + re-audit; structural → designer)?
│  └─ Does the loop continue until zero open annotations + explicit user acceptance?
│
├─ Step 10: Export (only when review-clean)
│  └─ Does the orchestrator ASK the user: PDF, PPTX, or both (with a recommendation)?
│  └─ PDF: batch_convert.py with --glob "[0-9]*.html" (element screenshots, never page.pdf)?
│  └─ PPTX: html2pptx.py; native shape groups for SVGs; verification checklist run?
│  └─ Filenames Title-YYYY-MM-DD.(pdf|pptx); page/slide count matches slide_count?
│  └─ Artifacts recorded in deck-metadata.json → exports?
│
└─ DONE: Verify all acceptance criteria
```

---

## What to Look For (Red Flags)

### Designer Self-Judging (❌ BAD)
Designer says: "I think this title should be an assertion. Let me revise it."  
**Problem:** Designer should NOT self-judge. Only auditors critique.  
**Fix:** Designer should generate based on brief, then auditors provide feedback.

### Incomplete Audit Reports (❌ BAD)
Brand audit says: "Slide is fine" (no table, no qa.py evidence)  
**Problem:** Should be one table with a row per finding, PASS rows for clean slides, a
summary line naming the qa.py result and the judgment findings.  
**Fix:** Audit should be thorough and specific — line numbers and the exact token/class.

### Re-running What Already Ran (❌ BAD)
Designer runs `qa.py` after every slide; brand-audit runs `validate.py` and
`check_contrast.py` per slide; orchestrator screenshots every slide at preview.  
**Problem:** The static verdict already arrived with each write; the chunk's batch `qa.py`
already ran; brand-audit's one `qa.py --deck-dir --json` is the evidence.  
**Fix:** One check per stage — see `references/hooks.md` for who runs what.

### Bloated Bookkeeping (❌ BAD)
`design-decisions.md` grows past 4 KB with paragraphs; designer writes a prose report per slide.  
**Problem:** Every agent re-reads that file on boot; prose reports are discarded.  
**Fix:** `log_slide.py` only (fixed table format); report = `--summary`.

### Circular Revision Loops (❌ BAD)
Designer → Brand Audit → Designer → Brand Audit → ... (>3 loops)  
**Problem:** Suggests initial generation quality is low.  
**Fix:** Investigate why designer isn't enforcing frameworks correctly on first pass.

### Vague Feedback from Design Crit (❌ BAD)
Design crit says: "This slide could be better"  
**Problem:** Feedback should be specific ("Title is a label; try 'Q2 delivery on track: 87% complete'").  
**Fix:** Design crit should always offer concrete suggestions.

### PDF Quality Issues (❌ BAD)
- Fonts render as a system fallback rather than the pack's own family
- Colors are wrong or washed out
- Images/SVGs are missing
- Page numbers aren't visible
- File is >20 MB (too large)

**Fix:** Check slide HTML (fonts loaded? gradients correct?) before rendering. If PDF quality is bad, usually a slide HTML issue, not a render issue.

---

## Testing Checklist (Per Test Case)

```
TEST CASE: [name]
Date: [date]
Tester: [you]

PRE-TEST
[ ] User request copied
[ ] Orchestrator skill path known: ./imprimatur/SKILL.md
[ ] Test case details available (expected output, acceptance criteria)

INTAKE PHASE
[ ] Orchestrator asks clarifying questions (if brief incomplete)
[ ] All 5 intake criteria locked in (audience, outcome, length, context, must-haves)
[ ] User approves structured brief

STRUCTURE PHASE
[ ] Orchestrator presents deck skeleton
[ ] Skeleton matches brief expectations
[ ] User approves structure

NARRATIVE PHASE
[ ] deck-narrative wrote narrative-outline.md itself (spawn prompt: header block + paths)
[ ] Visual concept briefs are complete (all fields incl. Visual:)
[ ] Visual count meets the VARIANCE dial; briefs align with narrative strategy

DESIGN PLAN (orchestrator, before any designer)
[ ] design-decisions.md holds Locked choices + one planned row per slide
[ ] plan_check.py PASS; deck-state.json seeded; stale NN-*.html archived

DESIGN PHASE (one agent per ≤ 5-slide chunk, all chunks spawned in the same turn)
[ ] Every slide created via new_slide.py (no Read of any templates/*.html), edited via Edit
[ ] STATIC PASS/FAIL visible after every slide write; FAILs fixed before the next slide
[ ] No qa.py / validate.py / fix_font_paths.py between slides; one qa.py batch per chunk
[ ] design-decisions.md + deck-state.json updated per slide via log_slide.py (rows, no prose)
[ ] Report = log_slide.py --summary + escalations; designer does NOT self-critique
[ ] Orchestrator verified from files: --summary, state-vs-disk diff, whole-deck qa.py --json

AUDIT PHASE (brand-audit ∥ design-crit, spawned together, read-only)
[ ] brand-audit: qa.py --deck-dir --json once (FAILs = audit FAILs); judgment rows checked;
    one table ≤ 40 lines with line numbers and exact fixes
[ ] design-crit: slide_body.py reads; ≤ 3 lines per slide; deck-level verdict from
    plan_check.py + named tells; feedback specific and actionable

REVISION PHASE
[ ] One merged fix list → one designer pass (≤ 3 fixes per spawn/message)
[ ] Re-checks script-only unless judgment finding + layout change; no auditor re-spawn
[ ] ≤ 2 rounds per stage, ≤ 2 cycles per slide; escalations surfaced

ASSEMBLY PHASE
[ ] All slides approved in deck-state.json
[ ] assemble_deck.py wrote index.html + deck-metadata.json; slide_count read back

RENDER PHASE (HTML preview)
[ ] One whole-deck qa.py --json; deck served over local HTTP; URL + summary handed over
[ ] No orchestrator screenshots; no "does this look good?" at this phase

REVIEW PHASE (the gate)
[ ] Review harness generated and offered to the user
[ ] Every annotation resolved or declined-with-reason (zero open)
[ ] User explicitly accepts before export

EXPORT PHASE
[ ] User asked to choose the format: PDF, PPTX, or both (orchestrator recommends per use)
[ ] PDF (if chosen): --glob "[0-9]*.html" element screenshots (not page.pdf); page count == slide_count; qlmanage spot-check
[ ] PPTX (if chosen): html2pptx.py; SVGs as native shape groups; pptx-export verification checklist; user opened it in PowerPoint
[ ] Filenames follow Title-YYYY-MM-DD.(pdf|pptx); artifacts recorded in deck-metadata.json → exports

VERIFICATION
[ ] All acceptance criteria met
[ ] Narrative flows cohesively
[ ] Design is consistent across slides
[ ] No red flags observed

RESULT
[ ] PASS: All criteria met, ready for production
[ ] FAIL: [list issues and next steps]
```

---

## If a Test Fails

**Step 1: Identify which phase failed**
- Intake? Structure? Narrative? Design? Audit? Assembly? Render?

**Step 2: Investigate the skill at that phase**
- Read the SKILL.md for that skill
- Check: Did it follow its own instructions?
- Check: Was input complete and clear?

**Step 3: Common fixes**
- **Narrative briefs incomplete?** → deck-narrative missing fields. Ask for clarification.
- **Designer generating low quality?** → Review brief; is it clear? Are frameworks understood?
- **Audits missing checks?** → Review audit SKILL.md; ensure all checks are run.
- **PDF quality issues?** → Check slide HTML; likely fonts or color issue, not render issue.

**Step 4: Document the issue**
- Which skill failed? What was the issue? What's the fix?
- Update the skill's SKILL.md if needed

**Step 5: Retest**
- Run the same test case again
- Verify fix worked

---

## After All 3 Tests Pass

**Congratulations!** Your pipeline is production-ready. Next steps:

1. **Archive test artifacts** (keep PDFs as examples)
2. **Update memory** (document any learnings or adjustments)
3. **Deploy the skills** (make available to yourself and team)
4. **Create a simple quickstart guide** (how to invoke orchestrator for a new deck)
5. **Start using it!** (create your first real deck)

---

## Success Metrics

You know the pipeline is working when:

✅ **All 3 test cases complete** with 0 red flags  
✅ **Designer never self-judges** (only iterates on audit feedback)  
✅ **Audit feedback is specific** (not vague, includes line numbers)  
✅ **Design quality is high** (focal points clear, hierarchy strong, messages assertive)  
✅ **Revision loops are short** (max 2 loops per slide)  
✅ **PDFs export cleanly** (no font/color/image issues)  
✅ **Narrative is cohesive** (deck tells one story, not 5 different messages)  

If all of these are true, you're ready for production.

---

## Questions During Testing

**Q: Designer is revising slides without auditor feedback. Is that OK?**  
A: No. Designer should generate once based on brief, then auditors tell them what to fix. Designer only iterates on feedback.

**Q: Brand-audit skipped the judgment rows and only pasted qa.py output. Is that OK?**  
A: No. The script is the evidence for the mechanical half; the four judgment rows (logo,
eyebrow, acronyms, gradient contrast) plus any named content check are the agent's whole
job. A clean qa.py run with no judgment rows is an incomplete audit.

**Q: The designer ran qa.py after each slide "to be safe". Is that OK?**  
A: No. The static verdict on each write is the per-slide check; the browser checks run once
per chunk and the stop gate enforces them. Per-slide qa.py is the 7-second-per-write cost
the batch model removed.

**Q: Design crit says "This could be better" but doesn't say how. Is that OK?**  
A: No. Feedback must be specific: "Title is a label; try 'X' instead" or "Focal point unclear; which element should the eye land on first?"

**Q: Revision loop went 5 times. Did something go wrong?**  
A: Probably. After 2–3 revision loops, something is structurally wrong (bad input, unclear brief, conflicting feedback). Investigate root cause.

**Q: PDF is 50 MB. Is that too large?**  
A: Yes. Likely a slide has an unoptimized image. Check slide HTML for large images; use SVG for diagrams instead.

---

## Contacts / Next Steps

- **Questions about a skill?** Read that skill's SKILL.md
- **Issue with the pipeline flow?** Check the orchestrator logic
- **Ready to deploy?** Copy all skills to your Claude Code skills directory (or equivalent)
- **Want to improve a skill?** Document the improvement and update the SKILL.md

Good luck! 🚀
