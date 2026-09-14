"""The SDG 15.3.1 Solara application.

This package is the UI. It builds a ``sdg1531.spec.RunSpec`` from user input,
validates it, and drives the domain's engine and statistics layers. It owns no
science: every computation lives in ``sdg1531``.

``__all__`` is empty and stays that way. Importing ``app`` must stay cheap --
the submodules pull in solara, pysepal and ee, and a re-export layer here would
drag all three into any import of the package name.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
