"""Dispatch diagram type -> builder. All recipes registered here."""
import importlib

_REGISTRY = {
    "donut":       "recipes.donut_builder",
    "bar":         "recipes.bar_builder",
    "line":        "recipes.line_builder",
    "pie":         "recipes.pie_builder",
    "flowchart":   "recipes.flowchart_builder",
    "timeline":    "recipes.timeline_builder",
    "funnel":      "recipes.funnel_builder",
    "pyramid":     "recipes.pyramid_builder",
    "process":     "recipes.process_builder",
    "cycle":       "recipes.cycle_builder",
    "matrix":      "recipes.matrix_builder",
    "gauge":       "recipes.gauge_builder",
    "kpi_cards":   "recipes.kpi_cards_builder",
    "hub_spoke":   "recipes.hub_spoke_builder",
    "venn":        "recipes.venn_builder",
    "org_chart":   "recipes.org_chart_builder",
    "area":        "recipes.area_builder",
    "radar":       "recipes.radar_builder",
    "stacked_bar": "recipes.stacked_bar_builder",
    "roadmap":     "recipes.roadmap_builder",
}

def get_builder(diagram_type):
    mod_path = _REGISTRY.get(diagram_type)
    if not mod_path:
        raise KeyError(
            f"No recipe for '{diagram_type}'. Available: {sorted(_REGISTRY)}. "
            f"If this pattern will recur, add recipes/<type>.md + "
            f"<type>_builder.py and register it here — see recipes/_generic.md "
            f"for the fallback approach in the meantime."
        )
    return importlib.import_module(mod_path).build

def register(diagram_type, module_path):
    _REGISTRY[diagram_type] = module_path

def available():
    return sorted(_REGISTRY)
