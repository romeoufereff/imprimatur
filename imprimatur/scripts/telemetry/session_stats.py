#!/usr/bin/env python3
"""
Per-session, per-agent telemetry (WP10) — ports `Tools/imprimatur-plan-telemetry/
analyze_sessions.py` + `agent_timeline.py` (the scripts used to produce the
optimization plan's §1 baseline table) into the engine, so every future WP can
be measured with the same script instead of a one-off during a review.

For the main session transcript AND every subagent transcript spawned from it
(`<session>/subagents/agent-*.jsonl`, each with an `agent-*.meta.json` sidecar
carrying `agentType` + `description`), reports:

  kind            — agentType from the .meta.json sidecar (or "main")
  turns           — assistant messages
  output_tok      — summed output_tokens
  cache_read_tok  — summed cache_read_input_tokens (the "cost of a long-lived
                    agent" the plan's baseline table tracks)
  ctx_peak        — largest single-turn (input + cache_creation + cache_read)
  minutes         — wall-clock span (first to last timestamped event)
  image_reads     — Read/tool_result entries carrying an image (PNG render checks)
  big_results     — tool_result payloads > 100KB (the WP7 "pathological read" signal)
  hook_visible    — True if any STATIC/QA PASS|FAIL text appears anywhere in the
                    transcript after a slide Write/Edit (WP1's acceptance signal —
                    the hook verdict actually reached the model, not just stdout)
  slide_cycle_s   — median seconds between consecutive slide-authoring tool calls
                    (Write to NN-*.html, or a new_slide.py Bash invocation)

Usage:
    session_stats.py <session-id-or-jsonl-path> [--json]

Resolution: an existing file path is used directly; otherwise the argument is
treated as a session id and searched for under `~/.claude/projects/*/`.
"""
import argparse
import datetime
import glob
import json
import os
import re
import statistics
import sys

SLIDE_RE = re.compile(r"^\d{2}-[\w.-]*\.html$")
HOOK_VERDICT_RE = re.compile(r"\b(?:STATIC|QA)\s+(?:PASS|FAIL)\b")
IMAGE_EXT_RE = re.compile(r"\.(?:png|jpe?g|gif|webp)$", re.I)


def ts(s):
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def resolve_main_path(arg):
    if os.path.isfile(arg):
        return os.path.abspath(arg)
    home = os.path.expanduser("~/.claude/projects")
    matches = glob.glob(os.path.join(home, "*", arg + ".jsonl"))
    if not matches:
        matches = glob.glob(os.path.join(home, "*", "*", arg + ".jsonl"))
    if not matches:
        sys.exit(f"error: no session transcript found for {arg!r} under {home}")
    return matches[0]


def find_agent_transcripts(main_path):
    """[(kind, jsonl_path, description), ...] for every subagent spawned from
    this session, plus ("main", main_path, None) first."""
    out = [("main", main_path, None)]
    session_dir = main_path[:-len(".jsonl")] if main_path.endswith(".jsonl") else main_path
    sub_dir = os.path.join(session_dir, "subagents")
    if not os.path.isdir(sub_dir):
        return out
    for jsonl_path in sorted(glob.glob(os.path.join(sub_dir, "agent-*.jsonl"))):
        meta_path = jsonl_path[:-len(".jsonl")] + ".meta.json"
        kind, desc = "?", None
        if os.path.isfile(meta_path):
            try:
                meta = json.load(open(meta_path, encoding="utf-8"))
                kind = meta.get("agentType", "?")
                desc = meta.get("description")
            except Exception:
                pass
        out.append((kind, jsonl_path, desc))
    return out


def analyze_transcript(path):
    turns = 0
    usage_sum = {"output_tokens": 0, "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0, "input_tokens": 0}
    ctx_peak = 0
    t0 = t1 = None
    image_reads = 0
    big_results = 0
    hook_visible = False
    slide_events = []  # (timestamp, label) for cycle-time computation
    pending_slide_write = False  # true right after a Write/Edit tool_use on a slide

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue

            t = ts(rec.get("timestamp", "")) if rec.get("timestamp") else None
            if t:
                t0 = t0 or t
                t1 = t

            msg = rec.get("message") or {}
            content = msg.get("content")

            if rec.get("type") == "assistant":
                turns += 1
                u = msg.get("usage") or {}
                for k in usage_sum:
                    usage_sum[k] += u.get(k, 0) or 0
                ctx = (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                      + u.get("cache_read_input_tokens", 0))
                ctx_peak = max(ctx_peak, ctx)

                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            name = block.get("name")
                            inp = block.get("input") or {}
                            if name in ("Write", "Edit"):
                                fp = os.path.basename(str(inp.get("file_path", "")))
                                if SLIDE_RE.match(fp):
                                    pending_slide_write = True
                                    if t:
                                        slide_events.append((t, fp))
                            elif name == "Bash":
                                cmd = str(inp.get("command", ""))
                                if "new_slide.py" in cmd and t:
                                    slide_events.append((t, "new_slide.py"))
                            elif name == "Read":
                                fp = str(inp.get("file_path", ""))
                                if IMAGE_EXT_RE.search(fp):
                                    image_reads += 1
                        elif block.get("type") == "text":
                            if HOOK_VERDICT_RE.search(block.get("text", "")):
                                if pending_slide_write:
                                    hook_visible = True

            elif rec.get("type") == "user" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    cc = block.get("content")
                    text_repr = json.dumps(cc) if cc else ""
                    size = len(text_repr)
                    if size > 100_000:
                        big_results += 1
                    if HOOK_VERDICT_RE.search(text_repr) and pending_slide_write:
                        hook_visible = True
                    if isinstance(cc, list):
                        for c in cc:
                            if isinstance(c, dict) and c.get("type") == "image":
                                image_reads += 1

            # additionalContext (WP1's PostToolUse hook shape) surfaces as a
            # top-level field on hook-emitted user/system events in some transcript
            # shapes — check generically wherever it appears on this record.
            add_ctx = rec.get("additionalContext")
            if add_ctx and HOOK_VERDICT_RE.search(str(add_ctx)) and pending_slide_write:
                hook_visible = True

    slide_events.sort(key=lambda e: e[0])
    cycle_times = [
        (b[0] - a[0]).total_seconds()
        for a, b in zip(slide_events, slide_events[1:])
        if (b[0] - a[0]).total_seconds() > 0
    ]
    minutes = (t1 - t0).total_seconds() / 60 if t0 and t1 else 0.0

    return {
        "turns": turns,
        "output_tok": usage_sum["output_tokens"],
        "cache_read_tok": usage_sum["cache_read_input_tokens"],
        "cache_creation_tok": usage_sum["cache_creation_input_tokens"],
        "ctx_peak": ctx_peak,
        "minutes": round(minutes, 1),
        "image_reads": image_reads,
        "big_results_gt100kb": big_results,
        "hook_visible": hook_visible,
        "slide_events": len(slide_events),
        "slide_cycle_s_median": round(statistics.median(cycle_times), 1) if cycle_times else None,
        "slide_cycle_s_all": [round(c, 1) for c in cycle_times],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("session", help="Session id, or a path to a session .jsonl file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    main_path = resolve_main_path(args.session)
    agents = find_agent_transcripts(main_path)

    rows = []
    for kind, path, desc in agents:
        stats = analyze_transcript(path)
        stats["kind"] = kind
        stats["description"] = desc
        stats["path"] = path
        rows.append(stats)

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    print(f"session: {main_path}")
    print(f"{'kind':28s} {'turns':>6s} {'out_tok':>9s} {'cache_read':>11s} "
          f"{'ctx_peak':>9s} {'min':>6s} {'img':>4s} {'>100KB':>7s} {'hook':>5s} "
          f"{'cycle_med_s':>11s}  description")
    for r in rows:
        print(f"{r['kind']:28.28s} {r['turns']:6d} {r['output_tok']:9d} "
              f"{r['cache_read_tok']:11d} {r['ctx_peak']:9d} {r['minutes']:6.1f} "
              f"{r['image_reads']:4d} {r['big_results_gt100kb']:7d} "
              f"{'yes' if r['hook_visible'] else 'no':>5s} "
              f"{(str(r['slide_cycle_s_median']) if r['slide_cycle_s_median'] is not None else '-'):>11s}  "
              f"{r['description'] or ''}")


if __name__ == "__main__":
    main()
