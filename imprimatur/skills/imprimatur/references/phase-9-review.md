# Phase 9 — Visual review & refine (detail)

This is the hard gate before export. Instead of a vague thumbs-up, the user marks up the
slides element by element in the `deck-review` harness, and you refine against those marks.
Full procedure: `{PLUGIN}/skills/deck-review/SKILL.md`.

## The loop

1. **Generate and serve the harness**

   ```bash
   python "{PLUGIN}/skills/deck-review/scripts/build_review.py" --deck-dir "<deck>" --title "<Deck Title>"
   ```

   Serving is the default; never pass `--no-serve` here. A `file://` harness cannot write to
   the deck folder, so comments would sit in the browser until an explicit export and get
   stranded. Served mode autosaves every comment into `<deck>/annotations.json`. The slide
   list comes from `deck-state.json`, so archived orphans never appear.

   Hand it over:
   > "I've opened a **review page** in your browser. In **Comment** mode, click any element
   > you'd like changed and type what to improve. In **Edit** mode you can change it yourself
   > — size, colour, gradient, spacing, or drag and resize — and I'll fold it into the slides
   > properly. Everything saves as you go; tell me when you're done. If it already looks good,
   > say so."

   The moment it is handed over, set `"review": { "offered": true }` in `deck-state.json`.
   This is what tells a resumed session — and `export_gate.py` — that the review round
   happened rather than being skipped.

2. **Read `annotations.json`** when the user says they are done. It carries written comments
   and `kind:"edit"` direct manipulations. **Run `apply_edits.py --deck-dir "<deck>"` first**
   so staged edits are materialised — until then the slide files show the pre-edit design.
   Promote each edit into real source (tokens/classes) per deck-review §2, resolve it, re-run
   the applier so its override drops out. Route each open comment:
   - **text-only comments on ≤ 3 slides** — apply them yourself with `Edit` (the static
     verdict arrives with each edit), then `qa.py --files <touched> --json`; no designer spawn;
   - **targeted asks** (resize / recolour / move / remove) — direct edits + `qa.py` on the
     touched slide; brand-audit judgment re-check only if a logo/eyebrow moved;
   - **structural asks** (new layout, split slide, add a visual, reorder) — one designer
     spawn per `phase-4-design.md` § Revision routing (batch the independent ones), then both
     auditors' judgment rows on the touched slides via targeted `SendMessage`, script checks
     for the rest.
   Mark each annotation `resolved` (one-line note) or `declined` (reason).

3. **Regenerate the harness** and ask for a re-review. Loop until **zero open comments** and
   the user accepts. Before calling the deck review-clean,
   `apply_edits.py --deck-dir "<deck>" --check` must exit 0 — no deck reaches export still
   carrying a `<style id="deck-review-edits">` staging block.

## What clears the gate

- The user reviewed in the harness and has **no open comments** (none added, or every one
  `resolved` / `declined`-with-reason), AND says "go ahead" / "export it".
- The harness was **generated and offered** (`review.offered` recorded) and the user chooses
  not to open it and says "looks good, no changes". Declining the offer is their right; the
  offer is not optional. The only path that skips generating it is a recorded §1 fast-track.

## What does not

- Any annotation still `open` in the latest `annotations.json`.
- No response, or "I'll check later".
- An acceptance given **before the harness was offered** — "looks good" at the §8 preview is
  feedback on the preview. Generate and offer the harness, then let them accept or decline
  with the review surface in hand.

## Done when

- [ ] Harness generated and handed over (or fast-track recorded per §1)
- [ ] `deck-state.json` carries `review.offered: true` (or `review.fast_track: true`)
- [ ] Every annotation `resolved` or `declined`-with-reason (zero `open`); `apply_edits.py --check` exits 0
- [ ] Touched slides re-checked (script for targeted edits; judgment rows for structural changes)
- [ ] User explicitly accepts; ready to ask PDF / PPTX / both
