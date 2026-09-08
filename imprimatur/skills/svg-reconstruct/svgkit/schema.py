"""Lightweight config validation, and the config loader every recipe builder uses.

load_config() is what makes a config file design-system-agnostic: a value written as
'role:primary' (or 'role:viz:0' for a list-valued role) is resolved against whatever
pack is currently active, the same way presets.py resolves its own constants. Without
this, a config's literal hex strings are frozen to whichever pack was active when
someone wrote the file — which is exactly the leak check_engine_clean.py exists to
catch, just at the config layer instead of the code layer.
"""

import json
import re

from . import presets

REQUIRED_TOP = {"type", "width", "height"}

_ROLE_RE = re.compile(r'^role:([\w-]+)(?::(\d+))?$')


def validate(config: dict):
    errors = []
    missing = REQUIRED_TOP - config.keys()
    if missing:
        errors.append(f"Missing top-level keys: {sorted(missing)}")
    if "type" in config and not isinstance(config["type"], str):
        errors.append("'type' must be a string")
    if errors:
        raise ValueError("Config invalid:\n- " + "\n- ".join(errors))
    return True


def _resolve(value):
    if isinstance(value, str):
        m = _ROLE_RE.match(value)
        if not m:
            return value
        name, idx = m.group(1), m.group(2)
        if idx is not None:
            seq = presets.resolve_role_list(name)
            i = int(idx)
            if i >= len(seq):
                raise ValueError(
                    f"config references 'role:{name}:{idx}' but the active pack's "
                    f"'{name}' role only has {len(seq)} colour(s) — pick an in-range "
                    f"index or add more to the pack's manifest")
            return seq[i]
        color = presets.resolve_role(name)
        if color is None:
            raise ValueError(
                f"config references 'role:{name}' but the active pack does not fill "
                f"that role — add it to the pack's manifest, or pick a role it "
                f"already declares (see design-system.json 'roles')")
        return color
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    return value


def load_config(config_path):
    """Load a recipe config JSON with every 'role:<name>' string resolved against the
    active design system. Recipes should call this instead of json.load directly —
    that's the one thing that keeps a shipped example config painting in whatever
    pack is active, instead of whichever pack was active when it was authored."""
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    return _resolve(cfg)
