"""One definition of "``maps`` is a different run now, throw the old one away".

``maps`` is a derivation of the run spec, so editing a parameter or the AOI
hands every output panel a NEW ``IndicatorMaps`` describing a DIFFERENT run.
Anything a panel still holds from the previous one -- a tile on the map, a
chart option, a table -- is then a picture of a run the user has moved on
from, under headings describing the current spec. Four panels need that rule,
and it must mean the same thing in all of them or the map and the charts
disagree about which run is on screen.

**The mount is not a change.** ``use_effect`` fires on mount too, and at mount
a panel holds nothing from a previous run by construction. Worse,
``MapLayersPanel``'s shared ``shown`` reactive outlives the component
(``page.py`` owns it), so a remount treating the CURRENT run's tiles as stale
would pull them off the map behind the user's back. Hence the ref.

``maps`` compares by IDENTITY -- the ee-bearing dataclasses carry ``eq=False``
(``sdg1531/engine/indicator.py``). Keep the dependency the whole ``maps``
object: a field of it would reintroduce the value comparison that ``eq=False``
exists to prevent.
"""

from __future__ import annotations

from collections.abc import Callable

import solara

__all__ = ("use_discard_on_new_run",)


def use_discard_on_new_run(run: object, discard: Callable[[], None]) -> None:
    """Call ``discard`` whenever ``run`` becomes a different run. Never on mount.

    ``run`` is the panel's ``maps`` -- including when it becomes ``None``,
    which is a run change like any other: the spec stopped being buildable, so
    whatever is still on screen describes a run that no longer exists.

    ``discard`` is read from the render in which ``run`` changed, so it closes
    over that render's values; it is not pinned to the mount's.
    """
    seen_a_run = solara.use_ref(False)

    def on_run_change() -> None:
        if not seen_a_run.current:
            seen_a_run.current = True
            return
        discard()

    solara.use_effect(on_run_change, [run])
