#!/usr/bin/env python3
"""
Per-session, per-agent telemetry — the measurement behind every performance
claim this plugin makes. First written for the 2026-09-02 optimization plan
(WP10); extended after the 2026-09-07 audit, which found that the numbers the
plan targeted were never re-measured and that two of its guarantees had never
switched on.

For the main session transcript AND every subagent transcript spawned from it
(`<session>/subagents/agent-*.jsonl`, each with an `agent-*.meta.json` sidecar
carrying `agentType` + `description`), reports:

  kind             agentType from the .meta.json sidecar (or "main")
  turns            assistant messages
  output_tok       summed output_tokens
  cache_read_tok   summed cache_read_input_tokens (the cost of a long-lived context)
  ctx_peak         largest single-turn (input + cache_creation + cache_read)
  minutes          wall-clock span
  images           image tool_results (each costs ~1.5 K tokens regardless of bytes)
  big_text         text tool_results > 20 K tokens (≈ 80 KB) — the pathological read signal
  hook_visible     True only if a `hook_additional_context` attachment carrying a
                   STATIC verdict exists. hook_success records do NOT count: they
                   prove the hook ran, not that the model saw its output.
  slides           slide-authoring events (Write to NN-*.html, or a new_slide.py call)
  turns/slide      turns ÷ slides, designer chunks only
  calls/slide      tool calls ÷ slides, designer chunks only
  slide_cycle_s    median seconds between consecutive slide-authoring events
  flags            main_wrote_slide · main_read_image · main_wrote_outline ·
                   validate_by_hand=N · qa_runs=N · legacy_hook=N

Plus a phase timeline derived from `Agent` spawns in the main transcript:
narrative → design (first designer spawn → last designer chunk end before the
audits) → audit (spawn → last auditor end), and the pipeline minutes from the
first designer spawn to the last auditor end — the "4a → review-ready" number.

Usage:
    session_stats.py <session-id-or-jsonl-path> [--json]
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
STATIC_RE = re.compile(r"\bSTATIC (?:PASS|FAIL|SKIP)\b")
IMAGE_EXT_RE = re.compile(r"\.(?:png|jpe?g|gif|webp)$", re.I)
BIG_TEXT_CHARS = 80_000  # ≈ 20 K tokens


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


def analyze_transcript(path, is_main=False):
    turns = 0
    tool_calls = 0
    usage_sum = {"output_tokens": 0, "cache_read_input_tokens": 0,
                 "cache_creation_input_tokens": 0, "input_tokens": 0}
    ctx_peak = 0
    t0 = t1 = None
    images = 0
    big_text = 0
    hook_visible = False
    slide_events = []   # (t, name) — one per authoring event, for cycle time
    slide_keys = set()  # distinct slide numbers authored, for turns/slide (never double-counted)
    spans = []          # per-slide spans: {"n", "calls", "turns", "bespoke"} from one new_slide.py to the next
    static_mentions = 0  # assistant text acknowledging a static verdict (subagent hook events leave no attachment)
    spawns = []
    flags = {"main_wrote_slide": 0, "main_read_image": 0, "main_wrote_outline": 0,
             "validate_by_hand": 0, "qa_runs": 0, "legacy_hook": 0}

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

            rtype = rec.get("type")
            if rtype == "attachment":
                att = rec.get("attachment") or {}
                if att.get("type") == "hook_additional_context":
                    content = att.get("content")
                    text = " ".join(content) if isinstance(content, list) else str(content or "")
                    if STATIC_RE.search(text):
                        hook_visible = True
                elif att.get("type") == "hook_success" and "/.claude/hooks/" in (att.get("command") or ""):
                    flags["legacy_hook"] += 1
                continue

            msg = rec.get("message") or {}
            content = msg.get("content")

            if rtype == "assistant":
                turns += 1
                if spans:
                    spans[-1]["turns"] += 1
                u = msg.get("usage") or {}
                for k in usage_sum:
                    usage_sum[k] += u.get(k, 0) or 0
                ctx = (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                       + u.get("cache_read_input_tokens", 0))
                ctx_peak = max(ctx_peak, ctx)
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text" and re.search(r"\bstatic (?:pass|fail)", block.get("text", ""), re.I):
                        static_mentions += 1
                    if block.get("type") != "tool_use":
                        continue
                    tool_calls += 1
                    name = block.get("name")
                    inp = block.get("input") or {}
                    # Credit a file-tool call to the span of the slide it touches (a chunk-end
                    # fix on slide 06 must not be billed to slide 07, whose span happens to be
                    # current); everything else goes to the current span.
                    span = spans[-1] if spans else None
                    if name in ("Write", "Edit", "Read"):
                        b = os.path.basename(str(inp.get("file_path", "")))
                        if SLIDE_RE.match(b):
                            for s in spans:
                                if s["n"] == b[:2]:
                                    span = s
                    if span is not None:
                        span["calls"] += 1
                    if name in ("Write", "Edit"):
                        fp = str(inp.get("file_path", ""))
                        base = os.path.basename(fp)
                        if SLIDE_RE.match(base):
                            if name == "Write":
                                if t:
                                    slide_events.append((t, base))
                                slide_keys.add(base[:2])
                                if span is not None:
                                    span["bespoke"] = True  # a full Write = bespoke host / >50 % rewrite
                                if is_main:
                                    flags["main_wrote_slide"] += 1
                        elif base == "narrative-outline.md" and name == "Write" and is_main:
                            flags["main_wrote_outline"] += 1
                    elif name == "Bash":
                        cmd = str(inp.get("command", ""))
                        if "new_slide.py" in cmd:
                            if t:
                                slide_events.append((t, "new_slide.py"))
                            m = re.search(r"--n\s+(\d+)", cmd)
                            key = f"{int(m.group(1)):02d}" if m else f"new{len(slide_keys)}"
                            slide_keys.add(key)
                            spans.append({"n": key, "calls": 1, "turns": 0, "bespoke": False})
                        if re.search(r"\bvalidate\.py\b", cmd):
                            flags["validate_by_hand"] += 1
                        if re.search(r"\bqa\.py\b", cmd):
                            flags["qa_runs"] += 1
                        if span is not None and re.search(r"recipe_brief|svgkit|_builder\.py|render\.py", cmd):
                            span["bespoke"] = True
                    elif name == "Read":
                        fp = str(inp.get("file_path", ""))
                        if IMAGE_EXT_RE.search(fp) and is_main:
                            flags["main_read_image"] += 1
                        if span is not None and re.search(r"\.svg$", fp, re.I):
                            span["bespoke"] = True  # a render look (.png) alone is not bespoke work
                    elif name == "Agent" and t:
                        spawns.append({"t": t, "type": inp.get("subagent_type"),
                                       "desc": inp.get("description"),
                                       "prompt_bytes": len(str(inp.get("prompt", "")))})

            elif rtype == "user" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    cc = block.get("content")
                    if isinstance(cc, list):
                        has_image = any(isinstance(c, dict) and c.get("type") == "image" for c in cc)
                        if has_image:
                            images += 1
                            continue
                    text_repr = json.dumps(cc) if cc else ""
                    if len(text_repr) > BIG_TEXT_CHARS:
                        big_text += 1

    slide_events.sort(key=lambda e: e[0])
    cycle = [(b[0] - a[0]).total_seconds() for a, b in zip(slide_events, slide_events[1:])
             if (b[0] - a[0]).total_seconds() > 0]
    minutes = (t1 - t0).total_seconds() / 60 if t0 and t1 else 0.0
    n_slides = len(slide_keys)
    # The last span also absorbs the chunk's batch qa + report; that is the honest cost of
    # the last slide's share, so it is not corrected for.
    template_spans = [s for s in spans if not s["bespoke"]]
    bespoke_spans = [s for s in spans if s["bespoke"]]

    return {
        "turns": turns,
        "tool_calls": tool_calls,
        "output_tok": usage_sum["output_tokens"],
        "cache_read_tok": usage_sum["cache_read_input_tokens"],
        "cache_creation_tok": usage_sum["cache_creation_input_tokens"],
        "ctx_peak": ctx_peak,
        "minutes": round(minutes, 1),
        "images": images,
        "big_text_results": big_text,
        "hook_visible": hook_visible,
        "slides": n_slides,
        "turns_per_slide": round(turns / n_slides, 1) if n_slides else None,
        "calls_per_slide": round(tool_calls / n_slides, 1) if n_slides else None,
        "slide_cycle_s_median": round(statistics.median(cycle), 1) if cycle else None,
        "slides_detail": spans,
        "calls_per_template_slide_median": round(statistics.median(s["calls"] for s in template_spans), 1) if template_spans else None,
        "calls_per_bespoke_slide_median": round(statistics.median(s["calls"] for s in bespoke_spans), 1) if bespoke_spans else None,
        "static_mentions": static_mentions,
        "flags": flags,
        "spawns": spawns,
        "t_start": t0.isoformat() if t0 else None,
        "t_end": t1.isoformat() if t1 else None,
    }


def phase_timeline(rows):
    """Derive narrative / design / audit phase windows from the main session's
    Agent spawns and the matching subagent transcript spans."""
    main = rows[0]
    spawns = main.get("spawns") or []
    agents = rows[1:]

    def ends(kind_substr, before=None):
        out = []
        for a in agents:
            if kind_substr in (a["kind"] or "") and a.get("t_end"):
                te = datetime.datetime.fromisoformat(a["t_end"])
                if before is None or te <= before:
                    out.append(te)
        return out

    def first_spawn(sub):
        for s in spawns:
            if sub in (s.get("type") or ""):
                return s["t"]
        return None

    d0 = first_spawn("deck-designer")
    a0 = first_spawn("brand-audit") or first_spawn("design-crit")
    n0 = first_spawn("deck-narrative")
    out = {}
    if n0:
        ne = ends("deck-narrative")
        out["narrative_min"] = round((min(ne) - n0).total_seconds() / 60, 1) if ne else None
    if d0:
        de = ends("deck-designer", before=a0) if a0 else ends("deck-designer")
        out["design_min"] = round((max(de) - d0).total_seconds() / 60, 1) if de else None
    if a0:
        ae = ends("brand-audit") + ends("design-crit")
        out["audit_min"] = round((max(ae) - a0).total_seconds() / 60, 1) if ae else None
        if d0 and ae:
            out["pipeline_min_design_to_audited"] = round((max(ae) - d0).total_seconds() / 60, 1)
    out["designer_spawns"] = sum(1 for s in spawns if "deck-designer" in (s.get("type") or ""))
    out["auditor_spawns"] = sum(1 for s in spawns if any(k in (s.get("type") or "")
                                                          for k in ("brand-audit", "design-crit")))
    out["max_prompt_bytes"] = max((s["prompt_bytes"] for s in spawns), default=0)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("session", help="Session id, or a path to a session .jsonl file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    main_path = resolve_main_path(args.session)
    rows = []
    for kind, path, desc in find_agent_transcripts(main_path):
        stats = analyze_transcript(path, is_main=(kind == "main"))
        stats["kind"] = kind
        stats["description"] = desc
        stats["path"] = path
        rows.append(stats)
    phases = phase_timeline(rows)

    if args.json:
        for r in rows:
            r["spawns"] = [{**s, "t": s["t"].isoformat()} for s in r.get("spawns", [])]
        print(json.dumps({"session": main_path, "phases": phases, "agents": rows},
                         indent=2, ensure_ascii=False))
        return

    print(f"session: {main_path}")
    print(f"{'kind':26s} {'turns':>5s} {'calls':>5s} {'out_tok':>8s} {'cache_read':>11s} "
          f"{'ctx_peak':>8s} {'min':>6s} {'img':>4s} {'big':>4s} {'hook':>5s} "
          f"{'t/sl':>5s} {'c/sl':>5s} {'cyc_s':>6s}  description")
    for r in rows:
        print(f"{r['kind']:26.26s} {r['turns']:5d} {r['tool_calls']:5d} {r['output_tok']:8d} "
              f"{r['cache_read_tok']:11d} {r['ctx_peak']:8d} {r['minutes']:6.1f} "
              f"{r['images']:4d} {r['big_text_results']:4d} "
              f"{'yes' if r['hook_visible'] else 'no':>5s} "
              f"{(str(r['turns_per_slide']) if r['turns_per_slide'] is not None else '-'):>5s} "
              f"{(str(r['calls_per_slide']) if r['calls_per_slide'] is not None else '-'):>5s} "
              f"{(str(r['slide_cycle_s_median']) if r['slide_cycle_s_median'] is not None else '-'):>6s}  "
              f"{r['description'] or ''}")
    m = rows[0]["flags"]
    print()
    for r in rows[1:]:
        if r.get("slides_detail"):
            det = " ".join(f"{s['n']}:{s['calls']}{'b' if s['bespoke'] else ''}" for s in r["slides_detail"])
            print(f"  {r['kind'].split(':')[-1]} [{(r['description'] or '')[:28]}] calls per slide → {det}   "
                  f"(template median {r['calls_per_template_slide_median']}, bespoke median "
                  f"{r['calls_per_bespoke_slide_median']}; static verdict acknowledged {r['static_mentions']}×)")
    print(f"main flags: wrote_slide={m['main_wrote_slide']} read_image={m['main_read_image']} "
          f"wrote_outline={m['main_wrote_outline']} validate_by_hand={m['validate_by_hand']} "
          f"qa_runs={m['qa_runs']} legacy_hook_fires={m['legacy_hook']}")
    agents_validate = sum(r["flags"]["validate_by_hand"] for r in rows[1:])
    print(f"agents: validate_by_hand={agents_validate} "
          f"images={sum(r['images'] for r in rows[1:])}")
    print(f"phases: {json.dumps(phases)}")


if __name__ == "__main__":
    main()
