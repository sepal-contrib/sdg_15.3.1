"""The app package exists, imports clean, and its catalogue is valid."""

from __future__ import annotations

import app
from app.message import messages


def test_app_exports_nothing():
    """`app` is a namespace, not a re-export layer: importing it must not
    pull in solara, pysepal or ee as a side effect of touching the package."""
    assert app.__all__ == ()


def test_the_catalogue_is_valid():
    """catalog() validates English at import; check() covers every other locale.

    ``missing_key`` (a locale simply has not caught up with English yet) is
    excluded: Task 14 owns translations and app.json's fr overlay is a
    deliberate partial one until then. Any other code -- placeholder
    mismatch, bad plural, shape mismatch -- is a real translation defect and
    must still be empty.
    """
    problems = tuple(p for p in messages.check() if p.code != "missing_key")
    assert problems == ()
