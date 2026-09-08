"""Every example config builds, and every icon it names exists.

The 20 example configs are the only executable specification of what each recipe
accepts. If one stops building, the recipe's `.md` schema and its builder have
drifted apart and the next reconstruction of that type starts from a broken example.
"""
import glob
import json
import os
import re
import xml.etree.ElementTree as ET

import pytest

from recipes.registry import get_builder
from svgkit import icons

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIGS = sorted(glob.glob(os.path.join(ROOT, "configs", "example_*.json")))


def test_there_are_configs():
    assert CONFIGS, "no example configs found — the fixtures are the spec"


@pytest.mark.parametrize("cfg_path", CONFIGS, ids=lambda p: os.path.basename(p)[8:-5])
def test_config_builds_well_formed_svg(cfg_path, tmp_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    build = get_builder(cfg["type"])
    out = tmp_path / (os.path.basename(cfg_path)[:-5] + ".svg")
    build(cfg_path, str(out))

    assert out.is_file() and out.stat().st_size > 0
    svg = out.read_text(encoding="utf-8")

    # Well-formed, not merely non-empty: a truncated f-string still writes a file.
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert root.get("viewBox"), "every reconstruction needs a viewBox to scale into a slide"

    # NaN in path data renders as nothing at all, silently — the failure mode this
    # package exists to prevent. Match it as a number, not as a substring: a bare
    # `"nan" in svg` also matches `dominant-baseline`, which is in every text element.
    assert not re.search(r'(?<![\w-])[-+]?nan(?![\w-])', svg, re.I), \
        "NaN in coordinates renders invisibly"
    assert not re.search(r'="[^"]*\bNone\b[^"]*"', svg), "a None leaked into an attribute"

    # An unresolved f-string placeholder still parses as XML and still renders — as the
    # wrong colour, silently. This caught a real one: a role substitution landed on a
    # plain string literal, so `fill="{presets.PRIMARY}"` shipped verbatim.
    leaked = re.findall(r'="\{[^"}]+\}"', svg)
    assert not leaked, f"unresolved placeholder(s) emitted: {sorted(set(leaked))}"

    # Every colour must be a real value, not a Python expression that leaked out.
    assert "presets." not in svg, "a presets.* reference was emitted instead of its value"


@pytest.mark.parametrize("cfg_path", CONFIGS, ids=lambda p: os.path.basename(p)[8:-5])
def test_every_icon_named_exists(cfg_path):
    """A missing icon name must not silently degrade to a placeholder shape — the
    icon-fidelity rule is the whole reason the curated set is bundled."""
    blob = open(cfg_path, encoding="utf-8").read()
    available = set(icons.available())
    for name in set(re.findall(r'"icon"\s*:\s*"([^"]+)"', blob)):
        assert name in available, (
            f"{os.path.basename(cfg_path)} names icon '{name}', which is not in the "
            f"built-in Lucide set. Add a real Lucide path to svgkit/icons.py._ICONS."
        )


def test_every_recipe_type_has_an_example():
    """A recipe with no example config is a recipe nobody can start from."""
    from recipes import registry
    covered = {json.load(open(c, encoding="utf-8"))["type"] for c in CONFIGS}
    registered = set(getattr(registry, "BUILDERS", {}) or {})
    if not registered:      # registry may expose it differently
        pytest.skip("registry does not expose its builder map")
    missing = registered - covered
    assert not missing, f"recipe types with no example config: {sorted(missing)}"


def test_builders_are_deterministic(tmp_path):
    """Same config in, same SVG out — the render-diff verify loop depends on it."""
    cfg_path = CONFIGS[0]
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    build = get_builder(cfg["type"])
    a, b = tmp_path / "a.svg", tmp_path / "b.svg"
    build(cfg_path, str(a))
    build(cfg_path, str(b))
    assert a.read_text() == b.read_text()
