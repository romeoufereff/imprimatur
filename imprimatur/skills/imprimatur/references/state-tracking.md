# State Tracking

How the orchestrator tracks progress across the 10-phase workflow — and how a fresh
session resumes a half-built deck.

**Design principle:** track only what a session actually reads and writes. State is two
artifacts: the **in-chat slide tracker** (working memory) and **`deck-state.json`**
(persistence between sessions, and the slide list every script reads).

---

## 1 · The slide tracker (in-chat, re-printed on every status change)

```
Deck: SAP BW Modernization (10 slides, Executive Pitch)
Dials: density=sparse, variance=high   ·   Brief: deck-brief.md
Last updated: [timestamp]

| # | Title | Template | Visual | Written | QA | Brand | Crit | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Cover | 01-cover | none | ✓ | PASS | PASS | PASS | ✓ approved | — |
| 3 | Problem | 03-two-column | none | ✓ | PASS | FAIL | — | ⚠️ revising | contrast on callout label |
| 6 | Proof | 42-data-chart | chart | ✗ | — | — | — | ⏳ pending | chunk 2 running |
```

### Slide status values (tracker ↔ `deck-state.json`)

| Tracker | JSON `status` | Meaning |
|---|---|---|
| `⏳ pending` | `pending` | Planned at 4a (template + visual locked), file not yet written |
| `🔄 written` | `written` | Designer created it (`log_slide.py`), chunk QA passed, awaiting audits |
| `⚠️ revising` | `revised` | A revision was applied; re-check pending or done |
| `✓ approved` | `approved` | Both audits clear; frozen unless a §9 comment touches it |

### Phase status values

`pending` · `in_progress` · `paused` (awaiting user: skeleton approval, review round,
acceptance) · `completed`.

---

## 2 · deck-state.json

Written into the deck folder **at every phase boundary** by the orchestrator, and
**per slide by the designer chunks** during phase 4 (`log_slide.py` upserts `slides[n]`
under a file lock, so parallel chunk agents never clobber each other). It is the resume
point for an interrupted session and the **slide list of record**: `qa.py --deck-dir`,
`build_review.py`, `assemble_deck.py`, `batch_convert.py` and `html2pptx.py` all take
their slide list from here when present (fallback: the `NN-*.html` glob), which is why
orphan files must be archived rather than left beside the deck (`phase-4-design.md` § 4b).

```json
{
  "deck": "SAP BW Modernization",
  "deck_path": "/…/Work/PharmaCore/Slides/SAP BW Modernization/",
  "phase": 6,
  "phase_name": "Revision Loops",
  "phase_status": "in_progress",
  "dials": { "density": "sparse", "variance": "high" },
  "updated_at": "2026-09-02T14:30:00Z",
  "slides": [
    { "n": 1, "file": "01-cover.html",   "title": "Cover",   "status": "approved",
      "template": "01-cover",            "visual": "none",  "updated_at": "2026-09-02T13:02:11Z" },
    { "n": 3, "file": "03-problem.html", "title": "Problem", "status": "revised",
      "template": "03-two-column-asymmetric", "visual": "none", "updated_at": "2026-09-02T14:21:40Z",
      "notes": "brand-audit contrast fail on callout label — fixed, script re-check pending" },
    { "n": 6, "file": "06-proof.html",   "title": "Proof",   "status": "pending",
      "template": "42-data-chart",       "visual": "chart", "updated_at": "2026-09-02T12:40:00Z" }
  ],
  "open_annotations": 0,
  "review": { "offered": false, "fast_track": false },
  "next_action": "script re-check slide 3; chunk 2 (slides 6-10) still running"
}
```

### Per-slide fields

| Field | Who writes it | Notes |
|---|---|---|
| `n` | orchestrator (4a) | integer, 1-based |
| `file` | orchestrator (4a) | `NN-slug.html`; the filename on disk |
| `title` | orchestrator (4a) | short human title from the skeleton |
| `status` | orchestrator (4a → `pending`; audits → `approved`), `log_slide.py` (`written`, `revised`) | `pending` \| `written` \| `revised` \| `approved` |
| `template` | orchestrator (4a), `log_slide.py` (confirms/overrides on escalation) | pack stem; host template for bespoke/chart |
| `visual` | orchestrator (4a), `log_slide.py` | `none` \| `chart` \| `pipeline` \| `bespoke` — `qa.py` uses it to scope the paint check and PNG render |
| `updated_at` | whoever last wrote the entry | ISO8601 |
| `notes` | orchestrator | optional, one line; the error log for that slide |

### Deck-level fields

- `phase` / `phase_name` / `phase_status` — 1–10 per the orchestrator workflow.
- `open_annotations` — count of `status: "open"` in `annotations.json` (0 before any
  review round). A human-readable mirror, not the gate's input: `export_gate.py` reads
  `annotations.json` directly. Keep it accurate anyway — it is what a resumed session reads first.
- `review.offered` — `true` the moment the §9 harness is generated and handed over.
  `review.fast_track` — `true` when the §1 fast-track legitimately skips the harness
  (internal + variance `low` + ≤ 7 slides). One of the two must be `true` before export;
  `export_gate.py` blocks a deck with no `annotations.json` and neither flag.
- `next_action` — one sentence; the single most useful field on resume.
- Companion files: `deck-brief.md` (intent), `design-decisions.md` (the plan and per-slide
  log, `templates/design-decisions-template.md`), `deck-metadata.json` (identity, written by
  `assemble_deck.py`). Do not duplicate their content here.

---

## 3 · Resuming a deck

When invoked on a folder that already contains `deck-state.json` + `deck-brief.md`:

1. Read both, plus `annotations.json` if present, and `log_slide.py --deck-dir D --summary`.
2. **Reconcile against reality** — list the `NN-*.html` files actually present and diff
   against `slides[]` (the one-liner in `phase-4-design.md` § 4d). Files win: a slide
   listed `pending` but present on disk means the state is stale; say so and correct it.
   A file not in `slides[]` is an orphan — archive it (§ 4b) rather than adopting it silently.
3. Re-print the tracker, state the recorded `next_action`, and confirm before continuing:
   *"Resuming at phase 6 — slide 3 mid-revision, chunk 2 not yet written. Continue?"*
4. Do **not** re-run intake or re-ask locked questions; `deck-brief.md` is the source of truth.
5. A chunk that was interrupted mid-way is re-spawned for its remaining `pending` slides
   only; already-`written` slides are not regenerated.

---

## 4 · Errors, retries, escalation

Failure handling lives with the workflow: revision limits, escalation triggers and per-skill
playbooks are in `escalation-and-errors.md`. When something fails, record it in the
tracker's `Notes` column and in `next_action`; that is the whole error log. If a failure
blocks a phase, set `phase_status: "paused"` and say what unblocks it.

## 5 · Update checklist

- [ ] Tracker re-printed after every status change
- [ ] `deck-state.json` written at every phase boundary and read back (verify side effects)
- [ ] During phase 4, chunk agents write their own slide entries via `log_slide.py` — confirm with `--summary` + the disk diff, never from a report alone
- [ ] `updated_at` refreshed on every write; ISO8601
- [ ] `open_annotations` synced after each review round
- [ ] `review.offered` set when the harness is handed over (or `review.fast_track` at §1)
- [ ] On resume: reconcile against files before trusting the state
