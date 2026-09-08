"""pytest entry point for the hook tests.

The hook tests are self-contained scripts (each prints PASS/FAIL lines and exits
non-zero on failure) so they run without pytest from validate_all.sh. This file
makes `pytest hooks/` collect them too — until 1.3.0 that command collected zero
tests, which the docs nonetheless recommended.
"""
import glob
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = sorted(p for p in glob.glob(os.path.join(HERE, "test_*.py"))
                 if not p.endswith("test_hooks_pytest.py"))


@pytest.mark.parametrize("script", SCRIPTS, ids=[os.path.basename(s) for s in SCRIPTS])
def test_hook_script(script):
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = os.path.dirname(HERE)
    proc = subprocess.run([sys.executable, script], capture_output=True, text=True, env=env, timeout=600)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
