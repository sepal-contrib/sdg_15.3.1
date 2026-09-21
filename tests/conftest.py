"""Shared paths for the domain test suite, and the offline ``ee`` fixture.

Two things only: ``REPO_ROOT``, so the suite imports ``sdg1531`` from the checkout
rather than from an install, and the session-scoped ``ee_offline`` fixture below
that Tier 3 and Tier 4 build every graph under.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# the domain package is imported from the checkout, so the suite runs before
# (and independently of) ``pip install -e .``
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from tests.ee_offline import initialize_offline_ee, load_ee_algorithms  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def ee_offline():
    """Initialise `ee` once per session with no network and no credentials.

    `autouse=True` is deliberate: the engine suites build `ee` objects inside plain helper
    functions (`make_resolved`, `_ctx()`, `_StubMaps.__init__`) that cannot request a
    fixture, and their tests never name `ee_offline`. Autouse gives every test in the
    suite an initialised `ee` before its body runs. A test may still take `ee_offline`
    as an argument to read back the pinned version string.

    Autouse does NOT cover `ee` objects built at module scope: those are constructed at
    import time, before any fixture runs. Tests that need such constants must build them
    inside a fixture, or in a helper called from the test body.
    """
    payload = load_ee_algorithms()
    initialize_offline_ee(payload["algorithms"])
    return payload["ee_version"]
