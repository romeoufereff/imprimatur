#!/usr/bin/env python3
"""
PostToolUse hook (matcher: Bash).

Fires a native macOS notification when a pdf-export/pptx-export command
(batch_convert.py, html2pptx.py) finishes — so a multi-second export doesn't
require staring at the terminal.

Reads the tool call (+ response) as JSON on stdin. Always exits 0.
"""
import json
import subprocess
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    # macOS-only by nature. Exit quietly elsewhere rather than raising FileNotFoundError
    # on every export — the hooks ship with the plugin and have to survive being shared.
    if sys.platform != "darwin":
        return 0

    cmd = payload.get("tool_input", {}).get("command", "") or ""
    if "batch_convert.py" in cmd:
        kind = "PDF"
    elif "html2pptx.py" in cmd:
        kind = "PPTX"
    else:
        return 0

    # Prefer the tool's own exit status. Substring-matching stderr for "Error" reported
    # successful exports as failed whenever a library wrote a routine warning.
    resp = payload.get("tool_response", {}) or {}
    if isinstance(resp, dict) and resp.get("exit_code") is not None:
        failed = resp.get("exit_code") != 0
    else:
        stderr_text = str(resp.get("stderr") or "") if isinstance(resp, dict) else ""
        failed = "Traceback (most recent call last)" in stderr_text
    status = "failed" if failed else "finished"

    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{kind} export {status}" with title "Claude Code — deck export"'],
            capture_output=True,
        )
    except Exception:
        # A missing osascript must never turn a successful export into a hook error.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
