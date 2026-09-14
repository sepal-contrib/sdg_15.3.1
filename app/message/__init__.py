"""The application's message catalogue.

English is the source of truth; every other locale is an overlay and a key it
lacks falls back to English. ``catalog()`` validates English at import, so a
structural mistake fails here rather than at the first render.
"""

from __future__ import annotations

from pathlib import Path

from pysepal.i18n import catalog

messages = catalog(Path(__file__).parent)
msg = messages.msg

__all__ = ("messages", "msg")
