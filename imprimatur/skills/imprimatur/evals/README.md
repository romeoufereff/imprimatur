# Evals

Two different things live here, graded two different ways.

## 1 · Scripted graders — `scripts/run_evals.py`

These run today and are part of `scripts/validate_all.sh`.

```bash
scripts/run_evals.py audit                      # recall + precision on the pack's seeded fixtures
scripts/run_evals.py designer <dir-of-slides>   # qa.py + per-slide assertions
scripts/run_evals.py narrative <briefs.md>      # SLIDE BRIEF field presence + visual-slide count
scripts/run_evals.py setup <id> <dir>           # stage one eval's isolated working folder
```

**`audit` is the one that matters most**, and it is the one `evals.json` has specified
since it was written without anything ever computing it. It runs `validate.py` and
`check_contrast.py` over the pack's `evals/stage-brand-audit/` fixtures and compares the
result against the recorded ground truth.

The failure it exists to catch is **fixture rot**, not a broken validator. A seeded fixture
is only ground truth while it contains exactly the seeded violations and nothing else — and
that has already failed once, when stale font paths and a dropped `data-template` added six
phantom failures per file and the eval had to be repaired rather than trusted. Any count
that does not match `expected_script_output` is treated as a false positive.

Each seed carries an explicit `scripted: true|false`. Read that field, not `detectable_by`,
which is prose — one seed's `detectable_by` names `validate.py` precisely in order to say
that validate.py does **not** catch it (a raw hex that is itself a sanctioned pack token
passes the palette census; the violation is that it was written inline rather than as a
token class, which no script checks).

Current: 6 of 10 seeds are script-detectable. The other 4 are the `brand-audit` agent's
job — logo placement, eyebrow format, acronym expansion — and no script should pretend
to score them.

## 2 · Stage and acceptance evals — `evals.json`

Nine evals needing a model in the loop. `run_evals.py setup <id> <dir>` stages the working
folder and prints the prompt; `run_evals.py designer|narrative` grades what comes back.

Stage evals (1–4, 6) are the ones to iterate on after changing an agent. Acceptance evals
(7–9) walk the full ten phases and are for before declaring a pipeline-wide change done.

## 3 · Trigger evals — `trigger-eval.json`

Twenty realistic queries — 9 that should reach this skill, 11 near-misses that should not.
The negatives are the valuable half: reading an existing `.pptx`, building an HTML
dashboard, exporting an already-reviewed deck, rebuilding one diagram, and — the closest
one — forging a design-system pack, which is `design-system-forge`'s job, not this one.

Run the optimiser with:

```bash
cd <skill-creator>
python3 -m scripts.run_loop \
  --eval-set   <plugin>/skills/imprimatur/evals/trigger-eval.json \
  --skill-path <plugin>/skills/imprimatur \
  --model      claude-opus-5 \
  --max-iterations 3 --verbose
```

It splits the set 60/40 train/test, runs each query three times for a stable trigger rate,
and selects on the held-out half so the description is not tuned to the queries it was
optimised against.

> **Requires a working `claude -p`.** The loop shells out to the CLI for every query. If
> the CLI cannot authenticate, every query returns nothing, the harness reads that as
> *did not trigger*, and you get a uniform 0/3 across positives and negatives alike — which
> looks like a catastrophically bad description rather than an auth failure. Check
> `echo hi | claude -p` first; the tell is that the **negative** cases "pass" too.

`design-system-forge` has its own `trigger-eval.json` built around the mirror-image
boundary: pack-building triggers it, deck-building does not.
