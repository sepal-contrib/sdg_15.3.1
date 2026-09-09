"""Shared paths for the domain test suite.

Deliberately tiny: the offline ``ee`` fixture that Tier 3 needs is added later,
in the engine scaffolding task, not here.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# the domain package is imported from the checkout, so the suite runs before
# (and independently of) ``pip install -e .``
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
