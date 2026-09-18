"""One definition of "``maps`` is a different run now, throw the old one away".

Task 20 made ``maps`` a derivation of the run spec: edit a parameter or the
AOI and ``page.py``'s ``use_memo`` hands every output panel a NEW
``IndicatorMaps`` describing a DIFFERENT run. Anything a panel is still
holding from the previous one -- a tile on the map, a chart option, a table --
is then a picture of a run the user has already moved on from, sitting under
headings that describe the current spec. That is the silently-wrong-data
failure the whole build-outcome design exists to prevent, and it reappears in
the panels unless each one discards on the same signal.

``MapLayersPanel`` had this logic inline; the repo owner then asked for the
rest of it -- *"if I change params, the map should gone and the graphs and
calculations should also gone, right? the same if I change the AOI"*. Four
panels needing the same rule is what makes it worth one hook rather than four
copies: "a different run" must mean the same thing in all of them, or the map
and the charts disagree about which run is on screen.

**The mount is not a change.** ``use_effect`` fires on mount as well as on a
real dependency change, and at mount a panel is holding nothing from a
previous run by construction. Worse, ``MapLayersPanel``'s shared ``shown``
reactive outlives the component (``page.py`` owns it), so a remount treating
the CURRENT run's own tiles as stale would take them off the map behind the
user's back. Hence the ref.

**``maps`` compares by identity, and the app depends on it.** The three
ee-bearing dataclasses carry ``eq=False`` (see
``sdg1531/engine/indicator.py``) because ``ee.ComputedObject.__eq__`` compares
``__dict__``: a generated field-by-field ``__eq__`` walks the whole graph, and
an ee graph is a DAG whose shared subtrees get re-walked once per path.

This is not an efficiency footnote. Reacton compares a component's props --
and the closure cells inside them -- with ``==`` on every reconciliation, and
``MapLayersPanel`` hands each row a callback closed over its
``ClassifiedLayer``. So before ``eq=False``, ANY spec edit that left one
layer's graph untouched (a threshold edit does not reach SOC) wedged the
kernel inside ``reacton.core._arguments_changed``, mid-render. Measured: two
structurally-equal SOC layers did not finish comparing in 8 seconds. What the
repo owner saw was the symptom -- *"that doesn't happen"* -- because the
render that would have cleared the map never finished. Identity equality is
also the right answer on its own terms: a rebuild is a new run.
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
