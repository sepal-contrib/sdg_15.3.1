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
    An empty tuple means no missing key, placeholder mismatch or bad plural."""
    assert messages.check() == ()
