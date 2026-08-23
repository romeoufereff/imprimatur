"""Locate the plugin root without counting directories.

Every script that needs a sibling file used to count `..` hops from its own
`__file__` — `os.path.join(dirname(__file__), "..", "..", "scripts")` and
friends. That works until a file moves one level, and then it fails silently by
resolving to a plausible-but-wrong directory rather than raising. The engine
already learned this lesson once with `@font-face` paths, which is why
`fix_font_paths.py` exists; this is the same fix applied to Python imports.

Anchor instead on the one directory that marks the plugin: `.claude-plugin/`.
Walk up from the caller until it appears. Depth becomes irrelevant, so moving a
script between `scripts/` and `skills/<name>/scripts/` costs nothing.

Usage:
    from _paths import plugin_root, engine_scripts, default_pack
"""

import os

MARKER = ".claude-plugin"


def plugin_root(start=None):
    """Nearest ancestor directory containing `.claude-plugin/`.

    Raises rather than guessing: a wrong root resolves to a directory that
    exists but holds the wrong pack, and that surfaces later as inexplicable
    design bugs instead of an import error.
    """
    here = os.path.abspath(start or __file__)
    if os.path.isfile(here):
        here = os.path.dirname(here)
    probe = here
    while True:
        if os.path.isdir(os.path.join(probe, MARKER)):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            raise RuntimeError(
                f"No {MARKER}/ found above {here}. The engine scripts must live "
                f"inside the plugin directory; check where this file was copied to."
            )
        probe = parent


def engine_scripts(start=None):
    """`<plugin root>/scripts` — the shared engine modules (ds_config, validate…)."""
    return os.path.join(plugin_root(start), "scripts")


def default_pack(start=None):
    """The design-system pack that ships beside the plugin.

    The repository holds two sibling folders — `imprimatur/` (this plugin) and
    `imprimatur-design-system/` (the pack it drives). A marketplace install
    clones the whole repository and points at the plugin sub-folder, so the
    sibling is present in an installed copy too.
    """
    return os.path.join(os.path.dirname(plugin_root(start)), "imprimatur-design-system")
