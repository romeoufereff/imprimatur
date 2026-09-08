import os
import sys

# The package is used by path, not installed, so the recipes and svgkit imports
# have to resolve from the skill root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
