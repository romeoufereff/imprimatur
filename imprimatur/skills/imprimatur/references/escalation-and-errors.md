# Escalation & Error Handling

Consolidated rules for revision limits, escalation triggers, decision-making, and per-skill
failure playbooks. The orchestrator SKILL.md carries a short summary; this file is the full
reference — read it when a loop stalls, an audit conflicts with the brief, or a sub-skill fails.

---

## Revision limits

**Max 2 revision cycles per slide** (initial draft + 1 revision cycle):

- **Cycle 1:** Designer drafts → audits → feedback provided
- **Cycle 2:** Designer revises → audits → feedback or approval
- **Cycle 3+:** STOP — escalate to user. A slide needing a 3rd cycle has a fundamental
  issue the designer can't resolve; that's a user decision, not another loop.

---

## Escalation triggers (act even before the 3rd cycle)

### Trigger 1 — Designer can't fit content (density overflow)

**Example:** "This brief asks for 8 bullets + 2 cards + 1 metric = 11 items against this
deck's sparse budget of 8."

1. Identify the conflict: designer says content doesn't fit the DENSITY dial; brief mandates it.
2. Ask narrative: "Which items are truly non-negotiable?"
3. Present options to the user: (a) simplify narrative, (b) split into two slides,
   (c) move lower-priority items to appendix.
4. User chooses → designer implements once → done (no re-audit needed for minor content cuts).

**Never let the designer shrink type to fit.** That violates the type-scale floors. Resolve
at the content level, not the pixel level.

### Trigger 2 — Same audit issue fails twice

**Example:** "Brand audit flagged color contrast FAIL on revision 1. Rev 2 fails the same test."

1. Stop the loop (don't send to rev 3).
2. Ask designer what the blocker is; if they can't explain, get the **explicit fix** from
   brand-audit (exact token, exact line).
3. Designer applies once → re-audit once → done.

### Trigger 3 — Audit feedback contradicts the brief

**Example:** design-crit says "too technical for an executive audience," but the brief says
executive and narrative delivered technical content per brief.

1. Flag to narrative: "Design feedback says 'too technical', brief says executive. Simplify,
   or keep the depth and justify it?"
2. Narrative decides: **simplify** (update brief → designer revises → re-audit both) or
   **keep** (justify in the brief, share with design-crit, designer proceeds).
3. One more cycle max, then approve.

### Trigger 4 — Auditors disagree with each other (rare)

**Example:** brand-audit passes a title; design-crit says it should be an assertion.

- Design-crit is probably right (it judges strategy, brand-audit judges mechanics) — but
  check the brief first: does narrative actually intend an assertion here?
- If yes → designer revises to assertion-evidence. If no → document the deviation, move on.

### Trigger 5 — A sub-skill raises concerns

If any sub-skill flags uncertainty ("this brief seems unrealistic", "this content may not
work for the stated audience"), **escalate to the user immediately** — don't override the
concern. Summarize the concern, show the options, get a decision. Human judgment on
judgment calls.

---

## Escalation process (how to present it)

1. **Summarize the conflict:** "Slide 3 (Architecture) is stuck: designer can't fit 11 items."
2. **Show the options:** "(a) simplify narrative, (b) split into two slides, (c) appendix."
3. **Get the decision.**
4. **Implement once and proceed** — no endless iteration; re-audit if needed, move on.

---

## Per-skill failure playbooks

### deck-narrative fails
Typical: "brief too vague", "outcome unclear", "must-haves contradict".
→ The error names what's missing; clarify that one thing with the user, update the brief,
retry once. Second failure on the same issue → ask the user to structure the skeleton manually.

### deck-designer fails
Typical: density overflow (→ Trigger 1), "invalid brief, missing fields" (→ push back to
narrative for the missing fields), "template mismatch".
→ Check brief realism first; if the brief is fine, ask the designer what specifically is
wrong and retry once. Second failure → escalate with full context (error + what was tried).

### brand-audit fails
Typical: malformed HTML (→ designer re-renders), missing asset (→ fix path, retry), specific
violation (→ pass the exact fix to the designer, retry once).
→ Same violation failing twice → Trigger 2.

### design-crit "fails"
Usually it's feedback, not failure. Critique contradicting the brief → Trigger 3. Real design
issue → pass to designer with the rationale. Same critique twice → ask design-crit for
specific remediation guidance before the next retry.

### The §8 HTML preview fails
Typical: missing slide file, stale `slides` array in index.html, fonts not loading.
→ Verify folder completeness against the add/remove-a-slide checklist (SKILL.md §7),
regenerate index.html, retry. Second failure → escalate with a folder listing.

### pdf-export fails
Typical: no files matching glob (→ check path), blue-rectangle gradient artifact (→ fonts
not reachable from filesystem root), wrong page count (→ `--slide-selector`), blank pages
(→ run `--debug` for per-slide PNGs).
→ One retry with `--debug`; still failing → share the error + a debug PNG with the user.

---

## Retry strategy

For **transient** failures (a served preview not coming up, a browser hiccup): retry once,
then ask the user. For **validation** failures (malformed data, missing fields): never
retry blind — fix the underlying input first, or escalate with context.

## Validation before every handoff

- [ ] Response is valid JSON or contains the expected file paths
- [ ] All mandatory fields present (not null, not empty)
- [ ] Referenced file paths point to actual files
- [ ] Content sanity (slide numbers 1–N, no duplicates)

If validation fails: don't proceed — ask the sub-skill for clarification or escalate.
