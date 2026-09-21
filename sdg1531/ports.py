"""The one port the domain declares: how it asks Earth Engine for a value.

The app passes pysepal's ``GEEInterface``, which satisfies this structurally
(``pysepal/scripts/gee_interface.py:193`` and ``:207``, checked against pysepal
3.8.3); the tests pass ``FakeFetcher``. Nothing here imports pysepal or ``ee``, so
``sdg1531`` stays installable and testable without either.

No EXPECTED_DIVERGENCES: a ``Protocol`` declaration and nothing else. The legacy had no
port; the transport change injecting one enables is
``sdg1531/stats/requests.py``'s note 1, recorded there.
"""

from __future__ import annotations

from typing import Any, Protocol

__all__ = ["InfoFetcher"]


class InfoFetcher(Protocol):
    """An awaitable ``getInfo``.

    The parameter names are load-bearing: a Protocol matches positional-or-keyword
    parameters by name, so ``ee_object`` and ``tag`` must stay spelled exactly as
    ``GEEInterface.get_info_async`` spells them. ``GEEInterface`` also takes a
    third keyword (``serialized_object``) with a default, which is why it still
    satisfies this narrower signature.

    Both methods are declared, but only :meth:`get_info_async` is called today --
    ``sdg1531.stats.api`` awaits one request at a time. The batch method is part of
    the port because it is where an Exception can arrive as a *value*:
    ``gee_interface.py:210`` gathers with ``return_exceptions=True``, whereas the
    single call re-raises (``:203-205``). ``stats/api.py``'s ``_unwrap`` handles
    both.
    """

    async def get_info_async(self, ee_object: Any = None, tag: Any = None) -> Any: ...

    async def get_info_batch_async(self, ee_objects: list[Any]) -> list[Any]: ...
