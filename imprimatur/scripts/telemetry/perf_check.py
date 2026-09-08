#!/usr/bin/env python3
"""
Performance regression check — asserts the TESTING-GUIDE thresholds against a
real session's telemetry and prints a PASS/FAIL list.

The 2026-09-02 plan set numeric targets and never checked them: the numbers
in the guide were aspirations, not measurements. This turns them into a gate
you run after every version bump on the 7-slide fixture (or any real deck):

    session_stats.py <session> --json | perf_check.py
    perf_check.py <session-id>

Thresholds (edit here, mirror in TESTING-GUIDE.md):
  designer chunk    template slides ≤ 8 tool calls (median) · bespoke slides ≤ 25 ·
                    ctx peak ≤ 250 K · validate.py by hand = 0 · static verdict
                    acknowledged in the designer's own text (subagent hook events leave
                    no transcript record, so the proof is behavioural)
  auditors          brand-audit ≤ 25 turns, ≤ 2 images · design-crit ≤ 25 turns, ≤ 1 image
  main              0 slide Writes · 0 image Reads · 0 narrative-outline Writes ·
                    0 legacy hook fires · ctx peak ≤ 250 K · spawn prompts ≤ 3 KB
  pipeline          first designer spawn → last auditor end ≤ 20 min (when both exist)

Exit 1 if any check fails.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

LIMITS = {
    "template_slide_calls": 8,    # new_slide → ranged Read → 2–4 Edits → log_slide (+ a share of the batch qa)
    "bespoke_slide_calls": 25,    # + recipe brief, config write, build, one render look, full Write, log
    "agent_ctx_peak": 250_000,
    "brand_audit_turns": 25,
    "brand_audit_images": 2,
    "design_crit_turns": 25,
    "design_crit_images": 1,
    "main_ctx_peak": 250_000,
    "spawn_prompt_bytes": 3_000,
    "pipeline_min": 20,
}


def load_stats(arg):
    if arg is None or arg == "-":
        return json.load(sys.stdin)
    out = subprocess.run([sys.executable, os.path.join(HERE, "session_stats.py"), arg, "--json"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(out.stderr or out.stdout)
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("session", nargs="?", help="Session id / path; omit or '-' to read session_stats --json from stdin")
    args = ap.parse_args()
    data = load_stats(args.session)
    agents = data["agents"]
    main_row = agents[0]
    checks = []

    def check(name, ok, detail):
        checks.append((name, bool(ok), detail))

    designers = [a for a in agents[1:] if "deck-designer" in (a["kind"] or "")]
    for a in designers:
        label = (a.get("description") or a["path"].split("/")[-1])[:40]
        det = a.get("slides_detail") or []
        # Per-slide tool calls, split by kind: a template slide is new_slide → one ranged
        # Read → a few Edits → log_slide; a bespoke slide legitimately adds a recipe build,
        # a render look and a full Write. Whole-chunk averages hid the difference.
        if a.get("calls_per_template_slide_median") is not None:
            check(f"template slides ≤ {LIMITS['template_slide_calls']} tool calls (median) [{label}]",
                  a["calls_per_template_slide_median"] <= LIMITS["template_slide_calls"],
                  f"{a['calls_per_template_slide_median']}  per slide: " +
                  " ".join(f"{s['n']}:{s['calls']}" for s in det if not s['bespoke']))
        if a.get("calls_per_bespoke_slide_median") is not None:
            check(f"bespoke slides ≤ {LIMITS['bespoke_slide_calls']} tool calls (median) [{label}]",
                  a["calls_per_bespoke_slide_median"] <= LIMITS["bespoke_slide_calls"],
                  f"{a['calls_per_bespoke_slide_median']}  per slide: " +
                  " ".join(f"{s['n']}:{s['calls']}" for s in det if s['bespoke']))
        check(f"designer validate.py by hand = 0 [{label}]",
              a["flags"]["validate_by_hand"] == 0, f"{a['flags']['validate_by_hand']}")
        check(f"designer ctx peak ≤ {LIMITS['agent_ctx_peak'] // 1000}K [{label}]",
              a["ctx_peak"] <= LIMITS["agent_ctx_peak"], f"{a['ctx_peak']}")
    # Hook visibility: a main-session slide edit leaves a hook_additional_context attachment;
    # a subagent's edits leave NO hook record in any transcript (verified 2026-09-07), so for
    # designers the evidence is behavioural — they acknowledge the verdict in their own text
    # and never run validate.py by hand.
    if main_row["flags"]["main_wrote_slide"] or main_row["hook_visible"]:
        check("static verdict reached the main session (hook_additional_context)", main_row["hook_visible"],
              "found" if main_row["hook_visible"] else "none found")
    if designers:
        acked = sum(a.get("static_mentions", 0) for a in designers)
        by_hand = sum(a["flags"]["validate_by_hand"] for a in designers)
        check("static verdict reached the designers (acknowledged in text, no validate.py by hand)",
              acked > 0 and by_hand == 0, f"acknowledged {acked}×, validate.py by hand {by_hand}")

    for a in agents[1:]:
        k = a["kind"] or ""
        if "brand-audit" in k:
            check("brand-audit turns ≤ 25", a["turns"] <= LIMITS["brand_audit_turns"], f"{a['turns']}")
            check("brand-audit images ≤ 2", a["images"] <= LIMITS["brand_audit_images"], f"{a['images']}")
        if "design-crit" in k:
            check("design-crit turns ≤ 25", a["turns"] <= LIMITS["design_crit_turns"], f"{a['turns']}")
            check("design-crit images ≤ 1", a["images"] <= LIMITS["design_crit_images"], f"{a['images']}")
        check(f"agent ctx peak ≤ 250K [{k.split(':')[-1]}]",
              a["ctx_peak"] <= LIMITS["agent_ctx_peak"], f"{a['ctx_peak']}")

    f = main_row["flags"]
    check("main wrote 0 slide files", f["main_wrote_slide"] == 0, f"{f['main_wrote_slide']}")
    check("main read 0 images", f["main_read_image"] == 0, f"{f['main_read_image']}")
    check("main wrote 0 narrative outlines", f["main_wrote_outline"] == 0, f"{f['main_wrote_outline']}")
    check("legacy hook fires = 0", f["legacy_hook"] == 0, f"{f['legacy_hook']}")
    check(f"main ctx peak ≤ {LIMITS['main_ctx_peak'] // 1000}K", main_row["ctx_peak"] <= LIMITS["main_ctx_peak"],
          f"{main_row['ctx_peak']}")
    phases = data.get("phases") or {}
    check("spawn prompts ≤ 3 KB", phases.get("max_prompt_bytes", 0) <= LIMITS["spawn_prompt_bytes"],
          f"{phases.get('max_prompt_bytes')}")
    if phases.get("pipeline_min_design_to_audited") is not None:
        check("pipeline design→audited ≤ 20 min", phases["pipeline_min_design_to_audited"] <= LIMITS["pipeline_min"],
              f"{phases['pipeline_min_design_to_audited']} min")

    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  ({detail})")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
