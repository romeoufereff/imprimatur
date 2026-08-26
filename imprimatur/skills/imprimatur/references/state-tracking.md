# State Tracking

How the orchestrator tracks progress across the 10-phase workflow — and how a fresh
session resumes a half-built deck.

**Design principle:** track only what a session actually reads and writes. Earlier
versions of this file specified checksums, handoff state machines, and rollback
protocols; none of that was ever executed and it eroded trust in the docs that are
real. State here is two artifacts: the **in-chat slide tracker** (working memory) and
**`deck-state.json`** (persistence between sessions).

---

## 1 · The slide tracker (in-chat, updated after every step)

The orchestrator keeps this table in its working context and re-prints it whenever
status changes. This is the canonical format (also shown in `SKILL.md` § State
Management):

```
Deck: SAP BW Modernization (10 slides, Executive Pitch)
Dials: density=sparse, variance=high   ·   Brief: deck-brief.md
Last updated: [timestamp]

| # | Title | Narrative | Designer | Brand Audit | Design Crit | Status | Notes |
|---|---|---|---|---|---|---|---|
| 1 | Cover | ✓ | ✓ | PASS | PASS | ✓ approved | — |
| 3 | Problem | ✓ | ✓ | FAIL | — | ⚠️ revising | Contrast fail, designer fixing |
| 6 | Proof | ✓ | ✗ | — | — | ⏳ pending | Awaiting designer |
```

### Slide status values

| Status | Meaning |
|---|---|
| `⏳ pending` | Brief exists, slide not yet generated |
| `🔄 auditing` | Drafted, one or both audits in progress |
| `⚠️ revising` | Audit feedback returned, designer working |
| `✓ approved` | Both audits passed; frozen unless a review comment touches it |

### Phase status values

| Status | Meaning |
|---|---|
| `pending` | Not started |
| `in_progress` | Currently executing |
| `paused` | Awaiting user input (skeleton approval, review round, acceptance) |
| `completed` | Done; next phase may start |

---

## 2 · deck-state.json (persisted at phase boundaries — and mid-batch by the agents themselves)

Write this file into the deck folder **at every phase boundary** and after any batch of
slide-status changes. It is the resume point for an interrupted session — without it, a
fresh session has to reverse-engineer progress from the files.

**Phases 4–5 are the exception to "the orchestrator writes it."** The designer,
brand-audit, and design-crit agents are each spawned once with the full N-slide batch and
don't report back to the orchestrator until the whole batch is done — so during those
phases, *the spawned agent* updates its own slide-level entries in `deck-state.json`
directly, right after finishing each slide, the same way it appends to
`design-decisions.md` as it goes. This is what keeps a mid-batch interruption resumable:
if the designer agent gets cut off after slide 6 of 10, `deck-state.json` still shows
slides 1–6 as written because the agent wrote that itself, not because the orchestrator
happened to be watching. The orchestrator re-syncs its own in-chat tracker from the file
once an agent's batch report lands, rather than writing the file turn by turn itself.

```json
{
  "deck": "SAP BW Modernization",
  "deck_path": "/…/Work/PharmaCore/Slides/SAP BW Modernization/",
  "phase": 6,
  "phase_name": "Revision Loops",
  "phase_status": "in_progress",
  "dials": { "density": "sparse", "variance": "high" },
  "updated_at": "2026-07-17T14:30:00Z",
  "slides": [
    { "n": 1, "file": "01-cover.html",   "title": "Cover",   "status": "approved" },
    { "n": 3, "file": "03-problem.html", "title": "Problem", "status": "revising",
      "notes": "brand-audit contrast fail on callout label" },
    { "n": 6, "file": "06-proof.html",   "title": "Proof",   "status": "pending" }
  ],
  "open_annotations": 0,
  "review": { "offered": false, "fast_track": false },
  "next_action": "designer revising slide 3; slides 6-7 not yet generated"
}
```

Field notes:
- `phase` / `phase_name` — 1–10 per the orchestrator workflow.
- `slides[].status` — `pending` / `auditing` / `revising` / `approved` (the tracker
  statuses, without the emoji).
- `open_annotations` — count of `status: "open"` entries in `annotations.json` (0 when
  no review round has run yet). This is a **human-readable mirror, not the gate's input**:
  `export_gate.py` reads `annotations.json` directly, so editing this number changes
  nothing. Keep it accurate anyway — it is what a resumed session reads first.
- `review.offered` — set `true` the moment the §9 harness is generated and handed to the
  user. `review.fast_track` — set `true` when the §1 fast-track legitimately skips the
  harness (internal + variance `low` + ≤7 slides). One of the two must be `true` before
  export: `export_gate.py` blocks any export from a deck with no `annotations.json` and
  neither flag set — that state means the review step was skipped, not passed.
- `next_action` — one human-readable sentence; the single most useful field on resume.
- Companion files: `deck-brief.md` (locked intent, written at intake) and
  `deck-metadata.json` (machine fields for render/export). Don't duplicate their
  content here — this file is about *progress*, those are about *intent* and *identity*.

### Resuming a deck

When invoked on a folder that already contains `deck-state.json` + `deck-brief.md`:

1. Read both, plus `annotations.json` if present.
2. **Reconcile against reality** — list the `NN-*.html` files actually present and
   diff against `slides[]`. Files win: a slide listed as `pending` but present on disk
   means the state file is stale; say so and correct it.
3. Re-print the slide tracker, state the recorded `next_action`, and confirm with the
   user before continuing: *"Resuming at phase 6 — slide 3 mid-revision, slides 6–7
   not yet generated. Continue from there?"*
4. Do **not** re-run intake or re-ask locked questions; `deck-brief.md` is the source
   of truth for intent.

---

## 3 · Errors, retries, and escalation

Failure handling lives with the workflow, not here:

- Per-slide revision limits (max 2 cycles), escalation triggers, and per-skill error
  playbooks: orchestrator `SKILL.md` § Revision Limits & Escalation and § Error
  Handling & Fallbacks.
- When something fails, record it in the tracker's `Notes` column and in
  `deck-state.json` → `next_action`; that's the whole error log. If a failure blocks a
  phase, set `phase_status: "paused"` and say what's needed to unblock.

## 4 · Update checklist

- [ ] Tracker re-printed after every slide status change
- [ ] `deck-state.json` written at every phase boundary (and read back — verify side effects)
- [ ] During phases 4–5, confirm the spawned agent is updating `deck-state.json` itself
      per slide (not just at batch end) — check this the same way you'd check
      `design-decisions.md` is being appended to
- [ ] `updated_at` refreshed on every write; ISO8601 timestamps
- [ ] `open_annotations` synced from `annotations.json` after each review round
- [ ] `review.offered` set when the §9 harness is handed over (or `review.fast_track` when §1 fast-track is invoked)
- [ ] On resume: reconcile state against files before trusting it
