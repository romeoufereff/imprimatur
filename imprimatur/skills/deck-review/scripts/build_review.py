#!/usr/bin/env python3
"""
build_review.py — generate a standalone visual review harness for a deck.

Reads the NN-*.html slides in a deck folder and serves a review harness so a reviewer can:
  - flip through the rendered slides,
  - click any element to attach a comment about what to improve,
  - have every comment autosaved to `<deck>/annotations.json` (the contract the
    deck-review skill refines against) — no Export click, nothing to remember.
  - switch to Edit mode and change an element directly: type step, weight, colour,
    alignment, padding/gap, radius — all drawn from the ACTIVE design system's own
    vocabulary — plus drag-to-move and resize handles snapped to the pack's grid.

Edit mode never rewrites a slide file. Each change is recorded as a selector ->
declaration patch in a `kind: "edit"` annotation (so it shares one status lifecycle,
one autosave path, and the existing export gate with ordinary comments) and projected
to `<deck>/edits.json`. `apply_edits.py` materialises those patches as an inline
`<style id="deck-review-edits">` block in each slide, so previews, PDF and PPTX all
honour them; the refine loop then promotes each edit into real source — tokens and
classes — and strips the block. The override layer is a staging area, never a
destination: an edit stays `status: "open"` until it has been promoted, and the
export gate already refuses to export a deck with open annotations.

Serving is the default because a file:// page cannot write to the deck folder at all;
it can only hold comments in localStorage until someone clicks Export. `--no-serve`
still produces that standalone build, with a warning, for when no server is possible.

Each slide renders inside a same-origin `<iframe srcdoc=…>`: srcdoc inherits the
parent origin, so the harness can read the slide DOM (compute selectors, place
badges) AND the slide's own Tailwind/canvas-scaler stay isolated from the harness UI.

Critical: slide HTML contains its own <script>…</script> (Tailwind CDN, the canvas
scaler, ECharts). When embedded in the harness's JSON <script> block, a raw
`</script>` would close the block early and corrupt the page. We escape every `</`
to `<\\/` before embedding — valid JSON (\\/ == /) and inert to the HTML parser.

Usage:
    # Default — serves the harness; annotations autosave into the deck folder.
    python build_review.py --deck-dir /path/to/deck [--port 8765] [--title "Deck Name"]

    # Escape hatch — standalone file://, requires an Export click, downloads to ~/Downloads.
    python build_review.py --deck-dir /path/to/deck --no-serve [--out /path/to/slide-review.html]
"""
import argparse
import json
import re
import sys
from pathlib import Path

SLIDE_RE = re.compile(r"^\d{2}-.*\.html$", re.IGNORECASE)


def collect_slides(deck_dir: Path) -> list[dict]:
    files = sorted(
        p for p in deck_dir.iterdir()
        if p.is_file() and SLIDE_RE.match(p.name) and p.name.lower() != "index.html"
    )
    slides = []
    for i, p in enumerate(files, start=1):
        slides.append({
            "file": p.name,
            "index": i,
            "html": p.read_text(encoding="utf-8", errors="replace"),
        })
    return slides


def load_vocabulary() -> dict:
    """The active design system's editable vocabulary — what Edit mode may offer.

    Read through the engine's ds_config so the properties panel is built from the
    pack in force (DECK_DESIGN_SYSTEM included) instead of hardcoding one brand's
    tokens. If the pack can't be read the panel simply offers nothing — Edit mode
    must never invent a value the design system doesn't sanction.
    """
    # Anchor on the plugin marker rather than a parents[N] index: this file has already
    # moved once, and a wrong index resolves to a directory that exists but holds nothing,
    # so the panel silently offers no tokens instead of failing.
    probe = Path(__file__).resolve().parent
    while not (probe / ".claude-plugin").is_dir():
        if probe.parent == probe:
            raise RuntimeError(f"No .claude-plugin/ above {Path(__file__).resolve()}")
        probe = probe.parent
    scripts = str(probe / "scripts")
    added = scripts not in sys.path
    if added:
        sys.path.insert(0, scripts)
    try:
        import ds_config
        return ds_config.load().editor_vocabulary()
    except Exception as e:  # noqa: BLE001
        print(f"Design system unreadable ({e}) — Edit mode will offer no tokens.", file=sys.stderr)
        return {}
    finally:
        if added and scripts in sys.path:
            sys.path.remove(scripts)


def load_seed(path: str | None) -> list:
    """Load existing annotations to pre-seed the harness (e.g. for a re-review round)."""
    if not path:
        return []
    p = Path(path).expanduser()
    if not p.exists():
        print(f"--annotations file not found: {p}", file=sys.stderr)
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("annotations", data) if isinstance(data, dict) else (data or [])
    except Exception as e:  # noqa: BLE001
        print(f"Could not parse --annotations {p}: {e}", file=sys.stderr)
        return []


def render_html(deck_dir: Path, title: str, seed: list | None = None) -> tuple[str, int]:
    from datetime import datetime, timezone
    slides = collect_slides(deck_dir)
    if not slides:
        print(f"No NN-*.html slides found in {deck_dir}", file=sys.stderr)
        sys.exit(1)
    data = {
        "deck": deck_dir.name,
        "title": title or deck_dir.name,
        "gen": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),  # scopes localStorage per generation
        "seed": seed or [],
        "ds": load_vocabulary(),
        "slides": slides,
    }
    # Escape </ so embedded slide </script> (and any </tag>) cannot close our script block.
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    # The harness chrome stays deliberately dark and neutral so it never competes with the
    # slide it frames — but its accents come from the active pack rather than from literals,
    # which is how the default pack's blue ended up hardcoded here.
    _ds = data["ds"] or {}
    _roles, _colors = _ds.get("roles", {}) or {}, _ds.get("colors", {}) or {}

    def _role(name, default):
        tok = _roles.get(name)
        return _colors.get(tok, default) if isinstance(tok, str) else default

    html = TEMPLATE.replace("__TITLE__", _html_escape(title or deck_dir.name))
    for token, value in (("__ACCENT__", _role("primary", "#3355DD")),
                         ("__ACCENT2__", _role("accent", _role("primary", "#3355DD"))),
                         ("__OPEN__", _role("caution", "#B4690E")),
                         ("__OK__", _role("positive", "#1A7F37"))):
        html = html.replace(token, value)
    html = html.replace("/*__DECK_DATA__*/", data_json)
    return html, len(slides)


def build(deck_dir: Path, out: Path, title: str, seed: list | None = None) -> None:
    html, n = render_html(deck_dir, title, seed)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({n} slides)")


def serve(deck_dir: Path, title: str, port: int, seed: list | None = None) -> None:
    """Serve the harness over localhost so the browser's Export writes annotations.json
    + annotations.md straight into the deck folder (POST /save), instead of downloading.
    Served from memory only — no slide-review.html is left on disk, so there is no
    file:// copy to open by mistake (that one would only download)."""
    import http.server
    import socketserver
    import json as _json
    import webbrowser
    import threading
    import mimetypes
    import os
    from urllib.parse import unquote, urlsplit

    html, n = render_html(deck_dir, title, seed)

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes = b"", ctype: str = "text/html; charset=utf-8") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html", "/slide-review.html"):
                self._send(200, html.encode("utf-8"))
                return
            # Serve any static file inside deck_dir (slide-referenced images etc.).
            # Slides render in srcdoc iframes that inherit this origin, so their
            # relative asset paths resolve here; without this branch they 404.
            rel = unquote(urlsplit(self.path).path).lstrip("/")
            root = os.path.realpath(deck_dir)
            target = os.path.realpath(os.path.join(root, rel))
            if target.startswith(root + os.sep) and os.path.isfile(target):
                ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
                with open(target, "rb") as f:
                    self._send(200, f.read(), ctype)
            else:
                self._send(404, b"not found")

        def do_POST(self) -> None:
            if self.path == "/edits":
                # Staged direct-manipulation patches. edits.json is the machine
                # contract apply_edits.py reads; edits.css is the same thing in
                # readable form, for eyeballing a diff. Both are removed when the
                # last edit is undone, so a cleared board leaves no stale file.
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    payload = _json.loads(self.rfile.read(length) or b"{}")
                    ej, ec = deck_dir / "edits.json", deck_dir / "edits.css"
                    if payload.get("empty"):
                        for p in (ej, ec):
                            if p.exists():
                                p.unlink()
                    else:
                        ej.write_text(payload.get("json", ""), encoding="utf-8")
                        ec.write_text(payload.get("css", ""), encoding="utf-8")
                    self._send(200, b'{"ok":true}', "application/json")
                except Exception as e:  # noqa: BLE001
                    self._send(500, str(e).encode("utf-8"))
                return
            if self.path != "/save":
                self._send(404, b"not found")
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = _json.loads(self.rfile.read(length) or b"{}")
                (deck_dir / "annotations.json").write_text(payload.get("json", ""), encoding="utf-8")
                (deck_dir / "annotations.md").write_text(payload.get("md", ""), encoding="utf-8")
                self._send(200, b'{"ok":true}', "application/json")
                print(f"Saved annotations.json + annotations.md -> {deck_dir}")
            except Exception as e:  # noqa: BLE001
                self._send(500, str(e).encode("utf-8"))

        def log_message(self, *args) -> None:  # quiet
            pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        url = f"http://127.0.0.1:{port}/"
        print(f"Serving review harness at {url}  ({n} slides)")
        print(f"Export in the browser now saves annotations.json + annotations.md into:\n  {deck_dir}")
        print("Press Ctrl+C to stop.")
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Review — __TITLE__</title>
<style>
  :root {
    --bg: #0f1115; --panel: #171a21; --line: #272b34; --ink: #e6e8ec;
    --muted: #9aa0aa; --accent: __ACCENT__; --accent2: __ACCENT2__; --open: __OPEN__; --ok: __OK__;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; }
  body { background: var(--bg); color: var(--ink); font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  #app { display: grid; grid-template-rows: auto 1fr; height: 100vh; }
  /* Topbar */
  #topbar { display: flex; align-items: center; gap: 14px; padding: 10px 16px; border-bottom: 1px solid var(--line); background: var(--panel); }
  #topbar .title { font-weight: 600; }
  #topbar .spacer { flex: 1; }
  .nav { display: flex; align-items: center; gap: 8px; }
  button { background: #222732; color: var(--ink); border: 1px solid var(--line); border-radius: 7px; padding: 6px 11px; cursor: pointer; font-size: 13px; }
  button:hover { border-color: #3a4150; }
  button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  button.primary:hover { filter: brightness(1.08); }
  .counter { color: var(--muted); min-width: 64px; text-align: center; }
  .pill { background: #222732; border: 1px solid var(--line); border-radius: 999px; padding: 3px 10px; color: var(--muted); font-size: 12px; }
  .pill b { color: var(--open); }
  /* Main */
  #main { display: grid; grid-template-columns: 1fr 360px; min-height: 0; }
  #stageWrap { position: relative; display: flex; align-items: center; justify-content: center; padding: 20px; min-width: 0; overflow: auto; }
  #stage { position: relative; width: 100%; max-width: calc((100vh - 150px) * 1.7778); aspect-ratio: 16 / 9; box-shadow: 0 8px 40px rgba(0,0,0,.5); background: #fff; }
  #frame { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: #fff; }
  #overlay { position: absolute; inset: 0; pointer-events: none; }
  .badge { position: absolute; transform: translate(-50%, -50%); width: 22px; height: 22px; border-radius: 50%; background: var(--open); color: #fff; font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 6px rgba(0,0,0,.5); pointer-events: auto; cursor: pointer; border: 2px solid #fff; }
  .badge.resolved { background: var(--ok); }
  .hint { position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%); color: var(--muted); font-size: 12px; background: rgba(0,0,0,.45); padding: 4px 10px; border-radius: 6px; }
  /* Side panel */
  #panel { border-left: 1px solid var(--line); background: var(--panel); display: flex; flex-direction: column; min-height: 0; }
  #panel header { padding: 12px 14px; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 8px; }
  #panel header .spacer { flex: 1; }
  #list { flex: 1; overflow: auto; padding: 8px; }
  .editor { border-bottom: 1px solid var(--line); padding: 12px 14px; background: #14171e; }
  .editor .target { font-size: 12px; color: var(--muted); margin-bottom: 6px; word-break: break-word; }
  .editor .target b { color: var(--ink); }
  textarea { width: 100%; min-height: 70px; resize: vertical; background: #0e1116; color: var(--ink); border: 1px solid var(--line); border-radius: 7px; padding: 8px; font: inherit; }
  .editor .row { display: flex; gap: 8px; margin-top: 8px; }
  .item { border: 1px solid var(--line); border-radius: 8px; padding: 9px 10px; margin-bottom: 8px; background: #14171e; }
  .item .head { display: flex; align-items: center; gap: 7px; margin-bottom: 4px; }
  .item .num { width: 20px; height: 20px; border-radius: 50%; background: var(--open); color: #fff; font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex: none; }
  .item .num.resolved { background: var(--ok); }
  .item .loc { font-size: 11px; color: var(--muted); flex: 1; word-break: break-word; }
  .item .cm { font-size: 13px; white-space: pre-wrap; }
  .item .acts { display: flex; gap: 8px; margin-top: 6px; }
  .item .acts button { padding: 2px 8px; font-size: 12px; }
  .empty { color: var(--muted); text-align: center; padding: 24px 12px; font-size: 13px; }
  .scope-slide { color: var(--accent2); }
  #toast { position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%); background: #14171e; border: 1px solid var(--line); color: var(--ink); padding: 10px 16px; border-radius: 8px; font-size: 13px; box-shadow: 0 8px 30px rgba(0,0,0,.6); opacity: 0; transition: opacity .2s; pointer-events: none; z-index: 50; max-width: 70vw; }
  #toast.show { opacity: 1; }
  /* ── Edit mode ─────────────────────────────────────────────── */
  .modes { display: flex; border: 1px solid var(--line); border-radius: 7px; overflow: hidden; }
  .modes button { border: 0; border-radius: 0; padding: 6px 12px; background: #222732; }
  .modes button.on { background: var(--accent); color: #fff; }
  .selbox { position: absolute; outline: 2px solid var(--accent); outline-offset: 0; pointer-events: auto; cursor: move; }
  .selbox.locked { outline-color: var(--muted); cursor: not-allowed; }
  .handle { position: absolute; width: 10px; height: 10px; background: #fff; border: 2px solid var(--accent); border-radius: 2px; pointer-events: auto; }
  .handle.nw { left: -6px; top: -6px; cursor: nwse-resize; }
  .handle.n  { left: calc(50% - 5px); top: -6px; cursor: ns-resize; }
  .handle.ne { right: -6px; top: -6px; cursor: nesw-resize; }
  .handle.e  { right: -6px; top: calc(50% - 5px); cursor: ew-resize; }
  .handle.se { right: -6px; bottom: -6px; cursor: nwse-resize; }
  .handle.s  { left: calc(50% - 5px); bottom: -6px; cursor: ns-resize; }
  .handle.sw { left: -6px; bottom: -6px; cursor: nesw-resize; }
  .handle.w  { left: -6px; top: calc(50% - 5px); cursor: ew-resize; }
  .editmark { position: absolute; width: 14px; height: 14px; border-radius: 3px; background: var(--accent2); border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,.5); pointer-events: none; transform: translate(-50%,-50%); }
  /* properties panel */
  #props { padding: 10px 14px 14px; overflow: auto; }
  #props .who { font-size: 12px; color: var(--muted); margin-bottom: 10px; word-break: break-word; }
  #props .who b { color: var(--ink); }
  #props .grp { margin-bottom: 12px; }
  #props .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: 5px; }
  #props .row2 { display: flex; gap: 8px; }
  #props select, #props input[type=number] { width: 100%; background: #0e1116; color: var(--ink); border: 1px solid var(--line); border-radius: 7px; padding: 6px 8px; font: inherit; }
  #props .sw { display: flex; flex-wrap: wrap; gap: 4px; }
  #props .sw button { width: 22px; height: 22px; padding: 0; border-radius: 5px; border: 1px solid #3a4150; }
  #props .sw button.on { outline: 2px solid var(--ink); outline-offset: 1px; }
  #props .sw button.none { background: repeating-linear-gradient(45deg,#333 0 4px,#555 4px 8px); font-size: 9px; color: #fff; }
  #props .sw button.grad { width: 38px; }
  #props .seg button:disabled { opacity: .4; cursor: not-allowed; }
  #props .seg { display: flex; gap: 0; }
  #props .seg button { border-radius: 0; flex: 1; }
  #props .seg button:first-child { border-radius: 7px 0 0 7px; }
  #props .seg button:last-child { border-radius: 0 7px 7px 0; }
  #props .seg button.on { background: var(--accent); border-color: var(--accent); color: #fff; }
  #props .acts { display: flex; gap: 8px; margin-top: 14px; }
  #props .note { font-size: 11px; color: var(--muted); margin-top: 10px; line-height: 1.5; }
  #props .warn { color: var(--open); }
  .item .num.edit { background: var(--accent2); border-radius: 4px; }
  .item .cm.editcm { color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<div id="app">
  <div id="topbar">
    <span class="title">📝 __TITLE__</span>
    <div class="modes">
      <button id="modeComment" class="on">Comment</button>
      <button id="modeEdit">Edit</button>
    </div>
    <span class="pill" id="countPill">0 comments</span>
    <div class="spacer"></div>
    <div class="nav">
      <button id="prev">← Prev</button>
      <span class="counter" id="counter">1 / 1</span>
      <button id="next">Next →</button>
    </div>
    <button id="slideComment">Comment on whole slide</button>
    <span class="pill" id="saveState" style="display:none;">✓ Saved</span>
    <button class="primary" id="export">Export annotations.json</button>
  </div>
  <div id="main">
    <div id="stageWrap">
      <div id="stage">
        <iframe id="frame" title="slide"></iframe>
        <div id="overlay"></div>
        <div class="hint" id="hint">Hover to highlight · click any element to comment</div>
      </div>
    </div>
    <div id="panel">
      <header>
        <strong id="panelTitle">Comments</strong>
        <span class="spacer"></span>
        <span id="undoRow" style="display:none;">
          <button id="undoBtn" title="Undo (⌘Z)" disabled>↶</button>
          <button id="redoBtn" title="Redo (⇧⌘Z)" disabled>↷</button>
        </span>
        <button id="clearAll" title="Remove all comments">Clear all</button>
      </header>
      <div id="props" style="display:none;"></div>
      <div class="editor" id="editor" style="display:none;">
        <div class="target" id="editorTarget"></div>
        <textarea id="editorText" placeholder="What should be improved here?"></textarea>
        <div class="row">
          <button class="primary" id="saveBtn">Save comment</button>
          <button id="cancelBtn">Cancel</button>
        </div>
      </div>
      <div id="list"></div>
    </div>
  </div>
</div>

<div id="toast"></div>

<script type="application/json" id="deck-data">/*__DECK_DATA__*/</script>
<script>
(function () {
  "use strict";
  const DATA = JSON.parse(document.getElementById("deck-data").textContent);
  const LSKEY = "deck-review:" + DATA.deck + ":" + (DATA.gen || "");
  const SERVED = location.protocol === "http:" || location.protocol === "https:";
  const frame = document.getElementById("frame");
  const overlay = document.getElementById("overlay");
  const counter = document.getElementById("counter");
  const countPill = document.getElementById("countPill");
  const listEl = document.getElementById("list");
  const editor = document.getElementById("editor");
  const editorTarget = document.getElementById("editorTarget");
  const editorText = document.getElementById("editorText");

  let cur = 0;                 // current slide index (0-based)
  let anns = load();           // all annotations
  let pending = null;          // element being commented (not yet saved)
  let editingId = null;        // id of annotation being edited
  let hoverEl = null;

  function load() {
    if (SERVED) return (DATA.seed || []).slice();   // served: deck-folder annotations.json is the truth
    try {
      const ls = JSON.parse(localStorage.getItem(LSKEY));
      if (ls && ls.length) return ls;       // file://: in-progress edits for this generation
    } catch (e) {}
    return (DATA.seed || []).slice();        // else the seeded annotations (e.g. a re-review round)
  }
  function save() {
    localStorage.setItem(LSKEY, JSON.stringify(anns));
    renderList(); renderBadges(); updateCount();
    if (SERVED) { autosave(); saveEdits(); } // served: persist to the deck folder on every change
  }
  let editTimer = null;
  function saveEdits() {
    clearTimeout(editTimer);
    editTimer = setTimeout(function () {
      const payload = editsPayload();
      const empty = !payload.edits.length;
      const css = Object.keys(payload.css).map(f => "/* " + f + " */\n" + payload.css[f]).join("\n\n");
      fetch("/edits", { method: "POST", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ empty: empty, json: JSON.stringify(payload, null, 2), css: css }) })
        .catch(function () { /* annotations.json already carries the edits; edits.json is a projection */ });
    }, 400);
  }
  let saveTimer = null;
  function autosave() {
    const st = document.getElementById("saveState");
    st.style.display = ""; st.innerHTML = "Saving…";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      const out = { deck: DATA.deck, created: new Date().toISOString(), annotations: anns };
      fetch("/save", { method: "POST", headers: { "Content-Type": "application/json" },
                       body: JSON.stringify({ json: JSON.stringify(out, null, 2), md: toMarkdown(out) }) })
        .then(function (r) { st.innerHTML = r.ok ? "✓ Saved to deck folder" : "save failed — retrying"; if (!r.ok) setTimeout(autosave, 1500); })
        .catch(function () { st.innerHTML = "save failed — retrying"; setTimeout(autosave, 1500); });
    }, 400);
  }
  function nextId() { let n = 1; const ids = new Set(anns.map(a => a.id)); while (ids.has("a" + n)) n++; return "a" + n; }

  function cssEsc(s) { return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/[^a-zA-Z0-9_-]/g, "\\$&"); }
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    if (el.id) return "#" + cssEsc(el.id);
    const parts = [];
    while (el && el.nodeType === 1 && el.tagName !== "BODY" && el.tagName !== "HTML") {
      if (el.id) { parts.unshift("#" + cssEsc(el.id)); break; }
      let seg = el.tagName.toLowerCase();
      const par = el.parentElement;
      if (par) {
        const same = Array.prototype.filter.call(par.children, c => c.tagName === el.tagName);
        if (same.length > 1) seg += ":nth-of-type(" + (same.indexOf(el) + 1) + ")";
      }
      parts.unshift(seg);
      el = el.parentElement;
    }
    return parts.join(" > ");
  }
  function snippet(el) { return (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 140); }

  // ---- slide rendering ----
  function renderSlide() {
    const s = DATA.slides[cur];
    frame.srcdoc = s.html;
    counter.textContent = (cur + 1) + " / " + DATA.slides.length;
    closeEditor();
  }
  frame.addEventListener("load", onFrameLoad);

  function onFrameLoad() {
    const doc = frame.contentDocument;
    if (!doc) return;
    // highlight style
    if (!doc.getElementById("__rev_style")) {
      const st = doc.createElement("style");
      st.id = "__rev_style";
      st.textContent = ".__rev_hl{outline:2px solid __ACCENT__ !important;outline-offset:1px;cursor:crosshair !important;}" +
                       ".__rev_sel{outline:2px solid __OPEN__ !important;outline-offset:1px;}";
      doc.head && doc.head.appendChild(st);
    }
    doc.addEventListener("mousemove", onHover, true);
    doc.addEventListener("mouseout", onOut, true);
    doc.addEventListener("click", onPick, true);
    // The staged overrides are injected into the slide document itself, which is
    // exactly what apply_edits.py inlines later — so what the reviewer sees here
    // and what the exported deck renders cannot drift apart.
    applyEditsToFrame();
    sel = null; drawSelection(); renderProps();
    renderBadges();
  }
  function onHover(e) {
    const el = e.target;
    if (el === hoverEl) return;
    if (hoverEl) hoverEl.classList.remove("__rev_hl");
    hoverEl = el;
    if (el && el.classList) el.classList.add("__rev_hl");
  }
  function onOut() { if (hoverEl) { hoverEl.classList.remove("__rev_hl"); hoverEl = null; } }
  function onPick(e) {
    e.preventDefault(); e.stopPropagation();
    const el = e.target;
    if (!el || el.nodeType !== 1) return;
    if (isEdit()) { selectEl(el); return; }
    pending = el; editingId = null;
    openEditor({
      scope: "element",
      selector: cssPath(el),
      tag: el.tagName.toLowerCase(),
      classes: (el.getAttribute && el.getAttribute("class")) || "",
      text_snippet: snippet(el),
    }, "");
  }

  // ---- editor ----
  function openEditor(target, comment) {
    editor.dataset.target = JSON.stringify(target);
    const where = target.scope === "slide"
      ? '<span class="scope-slide">Whole slide</span>'
      : "&lt;" + target.tag + "&gt; · <b>" + escapeHtml(target.text_snippet || "(no text)") + "</b>";
    editorTarget.innerHTML = "On: " + where;
    editorText.value = comment || "";
    editor.style.display = "block";
    editorText.focus();
  }
  function closeEditor() { editor.style.display = "none"; pending = null; editingId = null; }

  document.getElementById("saveBtn").addEventListener("click", function () {
    const comment = editorText.value.trim();
    if (!comment) { editorText.focus(); return; }
    const target = JSON.parse(editor.dataset.target);
    if (editingId) {
      const a = anns.find(x => x.id === editingId);
      if (a) a.comment = comment;
    } else {
      anns.push({
        id: nextId(),
        slide_file: DATA.slides[cur].file,
        slide_index: DATA.slides[cur].index,
        scope: target.scope,
        selector: target.selector || "",
        tag: target.tag || "",
        classes: target.classes || "",
        text_snippet: target.text_snippet || "",
        comment: comment,
        status: "open",
      });
    }
    closeEditor(); save();
  });
  document.getElementById("cancelBtn").addEventListener("click", closeEditor);

  document.getElementById("slideComment").addEventListener("click", function () {
    pending = null; editingId = null;
    openEditor({ scope: "slide", selector: "", tag: "", classes: "", text_snippet: "" }, "");
  });

  // ---- list + badges ----
  function annsForSlide() { return anns.filter(a => a.slide_index === DATA.slides[cur].index); }

  function renderList() {
    const here = annsForSlide();
    if (!anns.length) { listEl.innerHTML = '<div class="empty">No comments yet.<br>Click an element on the slide to add one.</div>'; return; }
    let html = "";
    DATA.slides.forEach(function (s) {
      const items = anns.filter(a => a.slide_index === s.index);
      if (!items.length) return;
      html += '<div style="color:var(--muted);font-size:11px;margin:6px 2px 4px;">Slide ' + s.index + ' — ' + escapeHtml(s.file) + '</div>';
      items.forEach(function (a) {
        const n = anns.indexOf(a) + 1;
        const loc = a.scope === "slide" ? '<span class="scope-slide">whole slide</span>'
          : "&lt;" + a.tag + "&gt; " + escapeHtml((a.text_snippet || "").slice(0, 60));
        const isEd = a.kind === "edit";
        html += '<div class="item">'
          + '<div class="head"><span class="num ' + (a.status === "resolved" ? "resolved" : (isEd ? "edit" : "")) + '">' + (isEd ? "✎" : n) + '</span>'
          + '<span class="loc">' + loc + '</span></div>'
          + '<div class="cm' + (isEd ? " editcm" : "") + '">' + escapeHtml(a.comment) + '</div>'
          + '<div class="acts">'
          + '<button data-go="' + a.id + '">Go to slide</button>'
          + '<button data-edit="' + a.id + '">Edit</button>'
          + '<button data-del="' + a.id + '">Delete</button>'
          + '</div></div>';
      });
    });
    listEl.innerHTML = html;
  }

  listEl.addEventListener("click", function (e) {
    const go = e.target.getAttribute("data-go");
    const ed = e.target.getAttribute("data-edit");
    const del = e.target.getAttribute("data-del");
    if (go) { const a = anns.find(x => x.id === go); if (a) { cur = a.slide_index - 1; renderSlide(); } }
    else if (ed) {
      const a = anns.find(x => x.id === ed); if (!a) return;
      if (a.slide_index - 1 !== cur) { cur = a.slide_index - 1; renderSlide(); }
      editingId = a.id;
      openEditor({ scope: a.scope, selector: a.selector, tag: a.tag, classes: a.classes, text_snippet: a.text_snippet }, a.comment);
    }
    else if (del) { anns = anns.filter(x => x.id !== del); save(); }
  });

  function renderBadges() {
    overlay.innerHTML = "";
    const doc = frame.contentDocument;
    if (!doc) return;
    annsForSlide().forEach(function (a) {
      if (a.kind === "edit") { if (isEdit()) editMark(a, doc); return; }
      if (a.scope === "slide" || !a.selector) return;
      let el = null;
      try { el = doc.querySelector(a.selector); } catch (e) { el = null; }
      if (!el) return;
      const r = el.getBoundingClientRect();
      const b = document.createElement("div");
      b.className = "badge" + (a.status === "resolved" ? " resolved" : "");
      b.textContent = String(anns.indexOf(a) + 1);
      b.style.left = (r.left + r.width / 2) + "px";
      b.style.top = (r.top + 6) + "px";
      b.title = a.comment;
      b.addEventListener("click", function () {
        editingId = a.id;
        openEditor({ scope: a.scope, selector: a.selector, tag: a.tag, classes: a.classes, text_snippet: a.text_snippet }, a.comment);
      });
      overlay.appendChild(b);
    });
  }

  function updateCount() {
    const open = anns.filter(a => a.status !== "resolved").length;
    const nEdits = anns.filter(a => a.kind === "edit").length;
    const nComments = anns.length - nEdits;
    countPill.innerHTML = nComments + " comment" + (nComments === 1 ? "" : "s")
      + (nEdits ? " · " + nEdits + " edit" + (nEdits === 1 ? "" : "s") : "")
      + (open ? ' · <b>' + open + " open</b>" : "");
  }

  // reposition badges when the slide iframe scrolls/resizes
  window.addEventListener("resize", function () { renderBadges(); drawSelection(); });
  frame.addEventListener("load", function () { setTimeout(renderBadges, 60); });

  // ---- export ----
  document.getElementById("export").addEventListener("click", function () {
    const out = { deck: DATA.deck, created: new Date().toISOString(), annotations: anns };
    const json = JSON.stringify(out, null, 2);
    const md = toMarkdown(out);
    const served = location.protocol === "http:" || location.protocol === "https:";
    if (served) {
      fetch("/save", { method: "POST", headers: { "Content-Type": "application/json" },
                       body: JSON.stringify({ json: json, md: md }) })
        .then(function (r) { if (!r.ok) throw new Error(); toast("Saved to the deck folder: annotations.json + annotations.md ✓"); })
        .catch(function () {
          download("annotations.json", json, "application/json");
          download("annotations.md", md, "text/markdown");
          toast("Server save failed — downloaded to your Downloads instead");
        });
    } else {
      download("annotations.json", json, "application/json");
      download("annotations.md", md, "text/markdown");
      toast("Downloaded to Downloads. To save straight into the deck folder, open via the served mode.");
    }
  });
  function toMarkdown(out) {
    let md = "# Review comments — " + DATA.title + "\n\n";
    DATA.slides.forEach(function (s) {
      const items = out.annotations.filter(a => a.slide_index === s.index);
      if (!items.length) return;
      md += "## Slide " + s.index + " — " + s.file + "\n\n";
      items.forEach(function (a, i) {
        md += "- **" + (a.kind === "edit" ? "✎ " + a.id : "#" + (out.annotations.indexOf(a) + 1)) + "** ("
          + (a.scope === "slide" ? "whole slide" : "`" + a.tag + "` — " + (a.text_snippet || "").slice(0, 60))
          + "): " + a.comment + "\n";
        if (a.kind === "edit" && a.decl) {
          Object.keys(a.decl).forEach(function (k) { md += "    - `" + k + ": " + a.decl[k] + "`\n"; });
        }
      });
      md += "\n";
    });
    return md;
  }
  function download(name, text, mime) {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
  }

  document.getElementById("clearAll").addEventListener("click", function () {
    if (anns.length && confirm("Remove all " + anns.length + " comments?")) { anns = []; save(); }
  });
  document.getElementById("prev").addEventListener("click", function () { if (cur > 0) { cur--; renderSlide(); } });
  document.getElementById("next").addEventListener("click", function () { if (cur < DATA.slides.length - 1) { cur++; renderSlide(); } });
  document.addEventListener("keydown", function (e) {
    const tag = document.activeElement && document.activeElement.tagName;
    if (document.activeElement === editorText || tag === "INPUT" || tag === "SELECT") return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
      e.preventDefault(); if (e.shiftKey) redo(); else undo(); return;
    }
    if (e.key === "Escape" && isEdit()) { sel = null; drawSelection(); renderProps(); return; }
    if (e.key === "ArrowLeft" && cur > 0) { cur--; renderSlide(); }
    else if (e.key === "ArrowRight" && cur < DATA.slides.length - 1) { cur++; renderSlide(); }
  });

  function escapeHtml(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

  let toastTimer = null;
  function toast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg; t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove("show"); }, 3200);
  }


  // ================= EDIT MODE =================
  // Direct manipulation, constrained to the design system's own vocabulary.
  // Every change is a selector -> declaration patch recorded as a kind:"edit"
  // annotation. Nothing here rewrites a slide file: apply_edits.py materialises
  // the patches as an inline <style> block, and the refine loop promotes them
  // into real source. The CSS built here is byte-for-byte what gets written, so
  // the harness preview and the exported deck cannot disagree.
  const DS = DATA.ds || {};
  const GRID = DS.gridPx || 8;
  const CANVAS_W = (DS.canvas && DS.canvas.width) || 1920;
  const SCALE_STEPS = Object.keys(DS.typeScale || {})
    .map(function (k) {
      const s = DS.typeScale[k];
      return { name: k, size: s.size, lineHeight: s.lineHeight, weight: s.fontWeight, px: parseFloat(s.size) };
    })
    .filter(function (s) { return !isNaN(s.px); })
    .sort(function (a, b) { return b.px - a.px; });
  const COLORS = DS.colors || {};
  const propsEl = document.getElementById("props");
  const panelTitle = document.getElementById("panelTitle");

  let mode = "comment";
  let sel = null;          // selected element inside the iframe
  let undoStack = [], redoStack = [];

  function isEdit() { return mode === "edit"; }
  function setMode(m) {
    mode = m;
    document.getElementById("modeComment").classList.toggle("on", m === "comment");
    document.getElementById("modeEdit").classList.toggle("on", m === "edit");
    document.getElementById("slideComment").style.display = m === "comment" ? "" : "none";
    document.getElementById("hint").textContent = m === "comment"
      ? "Hover to highlight · click any element to comment"
      : "Click to select · drag to move · handles resize · Alt = off-grid · Esc deselects";
    panelTitle.textContent = m === "comment" ? "Comments" : "Properties";
    propsEl.style.display = m === "edit" ? "" : "none";
    listEl.style.display = m === "edit" ? "none" : "";
    document.getElementById("undoRow").style.display = m === "edit" ? "" : "none";
    if (m !== "edit") { sel = null; }
    closeEditor(); drawSelection(); renderProps(); renderBadges();
  }

  // ---- edit records live in `anns` alongside comments -------------------
  // One store means one status lifecycle, one autosave path, and the export
  // gate blocks on an unpromoted edit for free (status stays "open").
  function nextEditId() { let n = 1; const ids = new Set(anns.map(a => a.id)); while (ids.has("e" + n)) n++; return "e" + n; }
  function editsForSlide() {
    const idx = DATA.slides[cur].index;
    return anns.filter(a => a.kind === "edit" && a.slide_index === idx);
  }
  function recFor(el) {
    if (!el) return null;
    const s = cssPath(el), idx = DATA.slides[cur].index;
    return anns.find(a => a.kind === "edit" && a.slide_index === idx && a.selector === s) || null;
  }
  function ensureRec(el) {
    let r = recFor(el);
    if (r) return r;
    // An override is only safe if its selector picks out exactly this element.
    // The harness is the only place that can check — apply_edits.py has no DOM —
    // so the count is recorded here and honoured there.
    const path = cssPath(el);
    let matches = 0;
    try { matches = frame.contentDocument.querySelectorAll(path).length; } catch (e) { matches = 0; }
    if (matches !== 1) {
      toast("This element can't be targeted uniquely (" + matches + " matches) — the edit is recorded but will not be applied. Comment on it instead.");
    }
    r = {
      selector_matches: matches,
      id: nextEditId(), kind: "edit",
      slide_file: DATA.slides[cur].file, slide_index: DATA.slides[cur].index,
      scope: "element", selector: cssPath(el), tag: el.tagName.toLowerCase(),
      classes: (el.getAttribute("class") || ""), text_snippet: snippet(el),
      decl: {}, intent: [], comment: "", status: "open",
    };
    anns.push(r);
    return r;
  }
  function setDecl(rec, prop, value, intent) {
    if (value === null || value === undefined || value === "") delete rec.decl[prop];
    else rec.decl[prop] = value;
    rec.intent = (rec.intent || []).filter(t => t.prop !== prop);
    if (intent) rec.intent.push(intent);
    rec.comment = intentSentence(rec);
    if (!Object.keys(rec.decl).length) anns = anns.filter(a => a !== rec);
  }
  function intentSentence(rec) {
    const parts = (rec.intent || []).map(function (t) {
      return t.note ? t.note : (t.prop + " " + (t.was || "?") + " -> " + t.now);
    });
    let s = "Direct edit — " + (parts.join("; ") || "styled");
    if (rec.userNote) s += ". Note: " + rec.userNote;
    return s;
  }

  // ---- the override CSS (identical to what apply_edits.py will inline) ----
  function cssForSlide(idx) {
    return anns
      .filter(a => a.kind === "edit" && a.slide_index === idx && a.status !== "declined"
                   && a.decl && Object.keys(a.decl).length)
      .map(function (a) {
        const body = Object.keys(a.decl).map(k => "  " + k + ": " + a.decl[k] + " !important;").join("\n");
        return "/* " + a.id + " */\n" + a.selector + " {\n" + body + "\n}";
      })
      .join("\n\n");
  }
  function applyEditsToFrame() {
    const doc = frame.contentDocument;
    if (!doc || !doc.head) return;
    let st = doc.getElementById("__rev_edits");
    if (!st) { st = doc.createElement("style"); st.id = "__rev_edits"; doc.head.appendChild(st); }
    st.textContent = cssForSlide(DATA.slides[cur].index);
  }
  function editsPayload() {
    const bySlide = {};
    DATA.slides.forEach(function (s) {
      const css = cssForSlide(s.index);
      if (css) bySlide[s.file] = css;
    });
    return {
      deck: DATA.deck, created: new Date().toISOString(),
      design_system: DS.id || "", grid_px: GRID,
      edits: anns.filter(a => a.kind === "edit"),
      css: bySlide,
    };
  }

  // ---- undo / redo -------------------------------------------------------
  function snapshot() {
    undoStack.push(JSON.stringify(anns));
    if (undoStack.length > 80) undoStack.shift();
    redoStack.length = 0;
    refreshUndo();
  }
  function undo() {
    if (!undoStack.length) return;
    redoStack.push(JSON.stringify(anns));
    anns = JSON.parse(undoStack.pop());
    sel = null; afterEditChange(true); refreshUndo();
  }
  function redo() {
    if (!redoStack.length) return;
    undoStack.push(JSON.stringify(anns));
    anns = JSON.parse(redoStack.pop());
    sel = null; afterEditChange(true); refreshUndo();
  }
  function refreshUndo() {
    document.getElementById("undoBtn").disabled = !undoStack.length;
    document.getElementById("redoBtn").disabled = !redoStack.length;
  }
  function afterEditChange(persist) {
    applyEditsToFrame(); drawSelection(); renderProps();
    if (persist) save(); else { renderList(); updateCount(); }
  }

  // ---- geometry ----------------------------------------------------------
  // #slide carries the pack's canvas scaler (transform: scale(r)), so screen
  // deltas are NOT slide pixels. Deriving the ratio from the live rect works
  // whether or not the scaler ran.
  function slideScale() {
    const doc = frame.contentDocument;
    if (!doc) return 1;
    const s = doc.getElementById("slide") || (doc.body && doc.body.firstElementChild);
    if (!s) return 1;
    const r = s.getBoundingClientRect();
    return r.width ? r.width / CANVAS_W : 1;
  }
  function parseTranslate(v) {
    const m = /translate\(\s*(-?[\d.]+)px\s*,\s*(-?[\d.]+)px\s*\)/.exec(v || "");
    return m ? { x: parseFloat(m[1]), y: parseFloat(m[2]) } : { x: 0, y: 0 };
  }
  function cstyle(el) {
    try { return frame.contentWindow.getComputedStyle(el); } catch (e) { return null; }
  }
  function isStructural(el) {
    if (!el || el.nodeType !== 1) return true;
    const t = el.tagName;
    return t === "HTML" || t === "BODY" || el.id === "slide";
  }
  // An element the slide itself transforms (rotated chevrons, scaled art) must not
  // be dragged: our translate would clobber the slide's own transform.
  function ownTransform(el, rec) {
    if (rec && rec.decl && rec.decl.transform) return false;
    const cs = cstyle(el);
    return !!(cs && cs.transform && cs.transform !== "none");
  }
  function canResize(el) {
    const cs = cstyle(el);
    return !!(cs && cs.display !== "inline");
  }

  // ---- selection ---------------------------------------------------------
  function selectEl(el) {
    if (isStructural(el)) { sel = null; drawSelection(); renderProps(); return; }
    sel = el;
    drawSelection(); renderProps();
  }
  function drawSelection() {
    Array.prototype.slice.call(overlay.querySelectorAll(".selbox")).forEach(n => n.remove());
    if (!isEdit() || !sel) return;
    const doc = frame.contentDocument;
    if (!doc || !doc.contains(sel)) { sel = null; return; }
    const r = sel.getBoundingClientRect();
    const rec = recFor(sel);
    const locked = ownTransform(sel, rec);
    const box = document.createElement("div");
    box.className = "selbox" + (locked ? " locked" : "");
    box.style.left = r.left + "px"; box.style.top = r.top + "px";
    box.style.width = r.width + "px"; box.style.height = r.height + "px";
    if (!locked) {
      box.addEventListener("mousedown", function (e) { startDrag(e, "move", ""); });
      if (canResize(sel)) {
        ["nw", "n", "ne", "e", "se", "s", "sw", "w"].forEach(function (d) {
          const h = document.createElement("div");
          h.className = "handle " + d;
          h.addEventListener("mousedown", function (e) { e.stopPropagation(); startDrag(e, "resize", d); });
          box.appendChild(h);
        });
      }
    }
    overlay.appendChild(box);
  }

  // Drags run in HARNESS space: the selection box lives in the overlay, so the
  // iframe never swallows the mousemove. Deltas are converted to slide pixels
  // through slideScale(); only deltas are used, so the frame offset cancels.
  function startDrag(e, kind, dir) {
    if (!sel) return;
    e.preventDefault(); e.stopPropagation();
    const k = slideScale();
    const rec = ensureRec(sel);
    const base = parseTranslate(rec.decl.transform);
    const r0 = sel.getBoundingClientRect();
    const startW = r0.width / k, startH = r0.height / k;
    const sx = e.clientX, sy = e.clientY;
    let moved = false;
    snapshot();
    frame.style.pointerEvents = "none";

    function snapv(v, free) { return free ? Math.round(v) : Math.round(v / GRID) * GRID; }
    function mm(ev) {
      const dx = (ev.clientX - sx) / k, dy = (ev.clientY - sy) / k;
      if (!moved && Math.abs(ev.clientX - sx) < 3 && Math.abs(ev.clientY - sy) < 3) return;
      moved = true;
      const free = ev.altKey;
      if (kind === "move") {
        const tx = snapv(base.x + dx, free), ty = snapv(base.y + dy, free);
        setDecl(rec, "transform", "translate(" + tx + "px, " + ty + "px)",
          { prop: "transform", was: "none", now: tx + "px, " + ty + "px",
            note: "moved " + tx + "px x / " + ty + "px y from its laid-out position" });
      } else {
        let w = startW, h = startH, tx = base.x, ty = base.y;
        if (dir.indexOf("e") >= 0) w = startW + dx;
        if (dir.indexOf("w") >= 0) { w = startW - dx; tx = base.x + dx; }
        if (dir.indexOf("s") >= 0) h = startH + dy;
        if (dir.indexOf("n") >= 0) { h = startH - dy; ty = base.y + dy; }
        if (dir.indexOf("e") >= 0 || dir.indexOf("w") >= 0) {
          w = Math.max(4, snapv(w, free));
          setDecl(rec, "width", w + "px",
            { prop: "width", was: Math.round(startW) + "px", now: w + "px" });
        }
        if (dir.indexOf("n") >= 0 || dir.indexOf("s") >= 0) {
          h = Math.max(4, snapv(h, free));
          setDecl(rec, "height", h + "px",
            { prop: "height", was: Math.round(startH) + "px", now: h + "px" });
        }
        if (dir.indexOf("w") >= 0 || dir.indexOf("n") >= 0) {
          const nx = snapv(tx, free), ny = snapv(ty, free);
          setDecl(rec, "transform", "translate(" + nx + "px, " + ny + "px)",
            { prop: "transform", was: "none", now: nx + "px, " + ny + "px",
              note: "resized from the " + dir + " edge, anchored" });
        }
      }
      afterEditChange(false);
    }
    function mu(ev) {
      document.removeEventListener("mousemove", mm, true);
      document.removeEventListener("mouseup", mu, true);
      frame.style.pointerEvents = "";
      if (!moved) {
        undoStack.pop(); refreshUndo();
        if (!Object.keys(rec.decl).length) anns = anns.filter(a => a !== rec);
        // A click that didn't drag drills into whatever is under the pointer,
        // so the selection box never blocks selecting a child.
        const fr = frame.getBoundingClientRect();
        const doc = frame.contentDocument;
        const under = doc && doc.elementFromPoint(ev.clientX - fr.left, ev.clientY - fr.top);
        if (under && under !== sel && !isStructural(under)) { selectEl(under); return; }
        drawSelection(); renderProps();
        return;
      }
      afterEditChange(true);
    }
    document.addEventListener("mousemove", mm, true);
    document.addEventListener("mouseup", mu, true);
  }

  // ---- properties panel --------------------------------------------------
  // Every control is built from the pack's vocabulary: the type ramp, the
  // sanctioned weights, the palette census, the spacing scale. A value the
  // design system does not define is a value this panel cannot author.
  function opt(v, label, on) {
    return '<option value="' + escapeHtml(v) + '"' + (on ? " selected" : "") + ">" + escapeHtml(label) + "</option>";
  }
  function renderProps() {
    if (!isEdit()) { propsEl.innerHTML = ""; return; }
    if (!sel) {
      propsEl.innerHTML = '<div class="empty">Click an element on the slide to edit it.<br><br>'
        + "Everything you change here is staged — I fold it into the slide source, on tokens, before export.</div>";
      return;
    }
    const cs = cstyle(sel);
    const rec = recFor(sel);
    const d = (rec && rec.decl) || {};
    const k = slideScale();
    const r = sel.getBoundingClientRect();
    const t = parseTranslate(d.transform);
    const curSize = Math.round(parseFloat((d["font-size"] || (cs && cs.fontSize)) || 0));
    const curWeight = String(parseInt(d["font-weight"] || (cs && cs.fontWeight) || 400, 10));
    const curAlign = d["text-align"] || (cs && cs.textAlign) || "";
    const locked = ownTransform(sel, rec);

    let h = '<div class="who">On <b>&lt;' + sel.tagName.toLowerCase() + "&gt;</b> "
      + escapeHtml((snippet(sel) || "(no text)").slice(0, 70)) + "</div>";

    // type ramp
    h += '<div class="grp"><div class="lbl">Type step</div><div class="row2">';
    let sizeSel = '<select id="pType">' + opt("", "— keep —", !d["font-size"]);
    SCALE_STEPS.forEach(function (s) {
      sizeSel += opt(s.name, s.name + "  ·  " + s.size, d["font-size"] === s.size);
    });
    sizeSel += "</select>";
    let wSel = '<select id="pWeight">' + opt("", "— keep —", !d["font-weight"]);
    (DS.weights || []).forEach(function (w) {
      wSel += opt(String(w), String(w), curWeight === String(w) && !!d["font-weight"]);
    });
    wSel += "</select>";
    h += sizeSel + wSel + "</div>";
    h += '<div class="note">Currently ' + curSize + "px / " + curWeight + "</div></div>";

    // colors
    h += '<div class="grp"><div class="lbl">Text colour</div><div class="sw" id="pFg">';
    h += '<button class="none' + (!d.color ? " on" : "") + '" data-c="">—</button>';
    Object.keys(COLORS).forEach(function (name) {
      h += '<button title="' + escapeHtml(DS.prefix + "-" + name) + '" data-c="' + COLORS[name]
        + '" class="' + (d.color === COLORS[name] ? "on" : "") + '" style="background:' + COLORS[name] + '"></button>';
    });
    h += "</div></div>";
    h += '<div class="grp"><div class="lbl">Background</div><div class="sw" id="pBg">';
    h += '<button class="none' + (!d["background-color"] ? " on" : "") + '" data-c="">—</button>';
    Object.keys(COLORS).forEach(function (name) {
      h += '<button title="' + escapeHtml(DS.prefix + "-" + name) + '" data-c="' + COLORS[name]
        + '" class="' + (d["background-color"] === COLORS[name] ? "on" : "") + '" style="background:' + COLORS[name] + '"></button>';
    });
    h += "</div></div>";

    // alignment
    h += '<div class="grp"><div class="lbl">Align</div><div class="seg" id="pAlign">';
    ["left", "center", "right"].forEach(function (a) {
      h += '<button data-a="' + a + '" class="' + (curAlign === a && d["text-align"] ? "on" : "") + '">' + a + "</button>";
    });
    h += "</div></div>";

    // spacing + radius
    const steps = DS.spacingSteps || [0, 8, 16, 24, 32];
    function stepSel(id, prop) {
      let s = '<select id="' + id + '">' + opt("", "— keep —", !d[prop]);
      steps.forEach(function (v) { s += opt(v + "px", v + "px", d[prop] === v + "px"); });
      return s + "</select>";
    }
    h += '<div class="grp"><div class="lbl">Padding · Gap</div><div class="row2">'
      + stepSel("pPad", "padding") + stepSel("pGap", "gap") + "</div></div>";
    let radSel = '<select id="pRadius">' + opt("", "— keep —", !d["border-radius"]) + opt("0px", "0px", d["border-radius"] === "0px");
    Object.keys(DS.radii || {}).forEach(function (n) {
      radSel += opt(DS.radii[n], n + "  ·  " + DS.radii[n], d["border-radius"] === DS.radii[n]);
    });
    radSel += "</select>";
    h += '<div class="grp"><div class="lbl">Radius</div>' + radSel + "</div>";

    // gradients — only the ones the pack declares, used only where it allows
    const GRADS = DS.gradients || {};
    const GPOL = DS.gradientPolicy || {};
    const gradNames = Object.keys(GRADS);
    if (gradNames.length) {
      const curGrad = d["background-image"] || "";
      const curName = gradTokenName(curGrad);
      const asText = !!d["-webkit-text-fill-color"];
      h += '<div class="grp"><div class="lbl">Gradient</div><div class="sw" id="pGrad">';
      h += '<button class="none' + (!curGrad ? " on" : "") + '" data-g="">—</button>';
      gradNames.forEach(function (n) {
        h += '<button class="grad ' + (curName === n ? "on" : "") + '" data-g="' + escapeHtml(n)
          + '" title="' + escapeHtml(DS.prefix + "-" + n) + '" style="background-image:' + GRADS[n] + '"></button>';
      });
      h += "</div>";
      if (curName) {
        const textOk = (GPOL.textAllowed || []).indexOf(curName) >= 0;
        h += '<div class="seg" id="pGradMode" style="margin-top:6px;">'
          + '<button data-gm="fill" class="' + (!asText ? "on" : "") + '">fill</button>'
          + '<button data-gm="text" class="' + (asText ? "on" : "") + '"' + (textOk ? "" : " disabled") + ">text</button>"
          + "</div>";
        h += '<div class="note">' + escapeHtml(DS.prefix + "-" + curName) + "</div>";
        if ((GPOL.decorative || []).indexOf(curName) >= 0) {
          h += '<div class="note warn">' + escapeHtml(GPOL.decorativeNote || "") + "</div>";
        }
        const words = (snippet(sel) || "").split(/\s+/).filter(Boolean).length;
        if (asText && GPOL.maxTextWords && words > GPOL.maxTextWords) {
          h += '<div class="note warn">' + words + " words — " + escapeHtml(GPOL.textNote || "") + "</div>";
        }
      }
      h += "</div>";
    }

    // geometry
    h += '<div class="grp"><div class="lbl">Offset X · Y (px)</div><div class="row2">'
      + '<input type="number" id="pX" step="' + GRID + '" value="' + t.x + '"' + (locked ? " disabled" : "") + ">"
      + '<input type="number" id="pY" step="' + GRID + '" value="' + t.y + '"' + (locked ? " disabled" : "") + ">"
      + "</div></div>";
    h += '<div class="grp"><div class="lbl">Width · Height (px)</div><div class="row2">'
      + '<input type="number" id="pW" step="' + GRID + '" value="' + Math.round(r.width / k) + '"' + (locked || !canResize(sel) ? " disabled" : "") + ">"
      + '<input type="number" id="pH" step="' + GRID + '" value="' + Math.round(r.height / k) + '"' + (locked || !canResize(sel) ? " disabled" : "") + ">"
      + "</div></div>";

    h += '<div class="acts"><button id="pComment">Comment on this</button>'
      + '<button id="pReset"' + (rec ? "" : " disabled") + ">Reset element</button></div>";
    if (locked) {
      h += '<div class="note warn">The slide already transforms this element, so moving it here would'
        + " clobber its own transform. Comment on it instead and I will change it in source.</div>";
    }
    if (rec) h += '<div class="note">Staged: ' + escapeHtml(rec.comment) + "</div>";
    propsEl.innerHTML = h;
    wireProps();
  }

  function wireProps() {
    const rec0 = function () { return ensureRec(sel); };
    const pType = document.getElementById("pType");
    if (pType) pType.addEventListener("change", function () {
      snapshot();
      const step = SCALE_STEPS.find(s => s.name === this.value);
      const rec = rec0();
      if (!step) { setDecl(rec, "font-size", null); setDecl(rec, "line-height", null); }
      else {
        const cs = cstyle(sel);
        const was = cs ? Math.round(parseFloat(cs.fontSize)) + "px" : "?";
        if (parseFloat(step.size) < (DS.minFontSizePx || 0)) { toast("Below the pack's " + DS.minFontSizePx + "px floor."); return; }
        setDecl(rec, "font-size", step.size,
          { prop: "font-size", was: was, now: step.size,
            note: "type step -> " + DS.prefix + "-" + step.name + " (" + was + " -> " + step.size + ")" });
        if (step.lineHeight) setDecl(rec, "line-height", step.lineHeight, null);
      }
      afterEditChange(true);
    });
    const pWeight = document.getElementById("pWeight");
    if (pWeight) pWeight.addEventListener("change", function () {
      snapshot();
      const cs = cstyle(sel);
      setDecl(rec0(), "font-weight", this.value || null,
        this.value ? { prop: "font-weight", was: cs ? cs.fontWeight : "?", now: this.value } : null);
      afterEditChange(true);
    });
    function swatches(id, prop, label) {
      const box = document.getElementById(id);
      if (!box) return;
      box.addEventListener("click", function (e) {
        const b = e.target.closest("button"); if (!b) return;
        snapshot();
        const hex = b.getAttribute("data-c");
        const cs = cstyle(sel);
        const was = cs ? (prop === "color" ? cs.color : cs.backgroundColor) : "?";
        const token = hex ? tokenName(hex) : "";
        setDecl(rec0(), prop, hex || null,
          hex ? { prop: prop, was: was, now: hex, note: label + " -> " + DS.prefix + "-" + token + " (" + hex + ")" } : null);
        afterEditChange(true);
      });
    }
    swatches("pFg", "color", "text colour");
    swatches("pBg", "background-color", "background");
    const pAlign = document.getElementById("pAlign");
    if (pAlign) pAlign.addEventListener("click", function (e) {
      const b = e.target.closest("button"); if (!b) return;
      snapshot();
      const rec = rec0(), a = b.getAttribute("data-a");
      const cs = cstyle(sel);
      setDecl(rec, "text-align", rec.decl["text-align"] === a ? null : a,
        rec.decl["text-align"] === a ? null : { prop: "text-align", was: cs ? cs.textAlign : "?", now: a });
      afterEditChange(true);
    });
    [["pPad", "padding"], ["pGap", "gap"], ["pRadius", "border-radius"]].forEach(function (pair) {
      const el = document.getElementById(pair[0]);
      if (!el) return;
      el.addEventListener("change", function () {
        snapshot();
        const cs = cstyle(sel);
        const was = cs ? cs.getPropertyValue(pair[1]) : "?";
        setDecl(rec0(), pair[1], this.value || null,
          this.value ? { prop: pair[1], was: was, now: this.value } : null);
        afterEditChange(true);
      });
    });
    function num(id, apply) {
      const el = document.getElementById(id);
      if (!el || el.disabled) return;
      el.addEventListener("change", function () { snapshot(); apply(Math.round(parseFloat(this.value) || 0)); afterEditChange(true); });
    }
    num("pX", function (v) {
      const rec = rec0(), t = parseTranslate(rec.decl.transform);
      setDecl(rec, "transform", "translate(" + v + "px, " + t.y + "px)",
        { prop: "transform", was: "none", now: v + "px, " + t.y + "px", note: "moved " + v + "px x / " + t.y + "px y from its laid-out position" });
    });
    num("pY", function (v) {
      const rec = rec0(), t = parseTranslate(rec.decl.transform);
      setDecl(rec, "transform", "translate(" + t.x + "px, " + v + "px)",
        { prop: "transform", was: "none", now: t.x + "px, " + v + "px", note: "moved " + t.x + "px x / " + v + "px y from its laid-out position" });
    });
    num("pW", function (v) {
      const k = slideScale(), was = Math.round(sel.getBoundingClientRect().width / k) + "px";
      setDecl(rec0(), "width", Math.max(4, v) + "px", { prop: "width", was: was, now: Math.max(4, v) + "px" });
    });
    num("pH", function (v) {
      const k = slideScale(), was = Math.round(sel.getBoundingClientRect().height / k) + "px";
      setDecl(rec0(), "height", Math.max(4, v) + "px", { prop: "height", was: was, now: Math.max(4, v) + "px" });
    });
    const pGrad = document.getElementById("pGrad");
    if (pGrad) pGrad.addEventListener("click", function (e) {
      const b = e.target.closest("button"); if (!b) return;
      snapshot(); applyGradient(rec0(), b.getAttribute("data-g"), false); afterEditChange(true);
    });
    const pGradMode = document.getElementById("pGradMode");
    if (pGradMode) pGradMode.addEventListener("click", function (e) {
      const b = e.target.closest("button"); if (!b || b.disabled) return;
      snapshot();
      const rec = rec0();
      applyGradient(rec, gradTokenName(rec.decl["background-image"] || ""), b.getAttribute("data-gm") === "text");
      afterEditChange(true);
    });
    const pReset = document.getElementById("pReset");
    if (pReset) pReset.addEventListener("click", function () {
      const rec = recFor(sel); if (!rec) return;
      snapshot();
      anns = anns.filter(a => a !== rec);
      afterEditChange(true);
    });
    const pComment = document.getElementById("pComment");
    if (pComment) pComment.addEventListener("click", function () {
      pending = sel; editingId = null;
      openEditor({ scope: "element", selector: cssPath(sel), tag: sel.tagName.toLowerCase(),
                   classes: sel.getAttribute("class") || "", text_snippet: snippet(sel) }, "");
    });
  }
  // The .gradient-text treatment as declarations: the pack clips the gradient to
  // the glyphs instead of painting a box. Only gradients the pack lists under
  // editor.gradients.textAllowed may be used that way — its decoration gradients
  // are washes, and reading text through one is exactly the slop the pack forbids.
  const GRAD_TEXT_PROPS = ["-webkit-background-clip", "background-clip", "-webkit-text-fill-color"];
  function gradTokenName(val) {
    const g = DS.gradients || {};
    const names = Object.keys(g);
    for (let i = 0; i < names.length; i++) if (g[names[i]] === val) return names[i];
    return "";
  }
  function applyGradient(rec, name, asText) {
    const pol = DS.gradientPolicy || {};
    const val = (DS.gradients || {})[name];
    GRAD_TEXT_PROPS.forEach(function (p) { setDecl(rec, p, null); });
    if (!val) { setDecl(rec, "background-image", null); reattach(rec); return; }
    if (asText && (pol.textAllowed || []).indexOf(name) < 0) {
      toast(pol.decorativeNote || "This gradient may not be clipped to text.");
      asText = false;
    }
    setDecl(rec, "background-image", val,
      { prop: "background-image", was: "none", now: DS.prefix + "-" + name,
        note: (asText ? "gradient text" : "gradient fill") + " -> " + DS.prefix + "-" + name });
    if (asText) {
      setDecl(rec, "-webkit-background-clip", "text", null);
      setDecl(rec, "background-clip", "text", null);
      setDecl(rec, "-webkit-text-fill-color", "transparent", null);
      const words = (snippet(sel) || "").split(/\s+/).filter(Boolean).length;
      if (pol.maxTextWords && words > pol.maxTextWords) {
        toast(words + " words on a gradient run — " + (pol.textNote || ""));
      }
    }
    reattach(rec);
  }
  // setDecl drops a record the moment its last declaration goes, so a multi-step
  // change (clear the text props, then set the fill) must put it back.
  function reattach(rec) {
    if (Object.keys(rec.decl).length && anns.indexOf(rec) < 0) anns.push(rec);
  }
  function tokenName(hex) {
    const names = Object.keys(COLORS);
    for (let i = 0; i < names.length; i++) if (COLORS[names[i]] === hex) return names[i];
    return hex;
  }

  // ---- wiring ------------------------------------------------------------
  document.getElementById("modeComment").addEventListener("click", function () { setMode("comment"); });
  document.getElementById("modeEdit").addEventListener("click", function () { setMode("edit"); });
  document.getElementById("undoBtn").addEventListener("click", undo);
  document.getElementById("redoBtn").addEventListener("click", redo);

  function editMark(a, doc) {
    let el = null;
    try { el = doc.querySelector(a.selector); } catch (e) { el = null; }
    if (!el) return;
    const r = el.getBoundingClientRect();
    const m = document.createElement("div");
    m.className = "editmark";
    m.style.left = (r.left + r.width) + "px";
    m.style.top = r.top + "px";
    m.title = a.comment;
    overlay.appendChild(m);
  }

  // ---- start ----
  if (SERVED) {
    // served mode: comments auto-save to the deck folder; the Export button is unnecessary
    document.getElementById("export").style.display = "none";
    const st = document.getElementById("saveState");
    st.style.display = ""; st.innerHTML = "✓ Saved to deck folder";
  }
  setMode("comment"); refreshUndo();
  renderSlide(); renderList(); updateCount();
})();
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a visual review harness for a deck.")
    ap.add_argument("--deck-dir", required=True, help="Folder containing NN-*.html slides")
    ap.add_argument("--out", default=None, help="Output path (default: <deck-dir>/slide-review.html)")
    ap.add_argument("--title", default=None, help="Deck title shown in the harness")
    # Serving is the DEFAULT, and --serve is kept only so existing callers don't break.
    # Rationale: a page opened from file:// physically cannot write to the deck folder —
    # the browser forbids it — so a standalone harness can only hold comments in
    # localStorage and hand them over on an explicit Export click. That click is a step
    # a reviewer should never have to know about, and skipping it silently strands their
    # markup in a browser tab (observed: two comments lost because the harness was built
    # without --serve). Served mode autosaves every change into <deck>/annotations.json,
    # which is what every downstream step — the refine loop and the export gate — reads.
    ap.add_argument("--serve", action="store_true",
                    help="(default) Serve over localhost so annotations autosave into the deck folder")
    ap.add_argument("--no-serve", dest="no_serve", action="store_true",
                    help="Write a standalone file:// harness instead. Comments then live in the "
                         "browser until the reviewer clicks Export, which downloads them to "
                         "~/Downloads — they do NOT reach the deck folder. Use only when a local "
                         "server is impossible.")
    ap.add_argument("--port", type=int, default=8765, help="Port for the server (default 8765)")
    ap.add_argument("--annotations", default=None,
                    help="Pre-seed the harness with an existing annotations.json (e.g. a re-review round)")
    args = ap.parse_args()

    deck = Path(args.deck_dir).expanduser().resolve()
    if not deck.is_dir():
        print(f"Deck dir not found: {deck}", file=sys.stderr); sys.exit(1)
    # default seed: the deck's own annotations.json if present (so re-runs resume automatically)
    seed_path = args.annotations or (str(deck / "annotations.json") if (deck / "annotations.json").exists() else None)
    seed = load_seed(seed_path)
    if args.no_serve:
        out = Path(args.out).expanduser().resolve() if args.out else deck / "slide-review.html"
        build(deck, out, args.title, seed)
        print("\nWARNING: standalone (file://) harness. Comments stay in the browser and reach\n"
              "         the deck folder ONLY if the reviewer clicks Export, which downloads to\n"
              "         ~/Downloads. Nothing autosaves. Prefer the default served mode.",
              file=sys.stderr)
    else:
        serve(deck, args.title, args.port, seed)


if __name__ == "__main__":
    main()
