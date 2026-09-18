"""The one definition of "``maps`` is a different run now".

Four panels discard on this signal, so it is worth testing once, directly,
rather than four times through whatever each panel happens to hold.
"""

from __future__ import annotations

from typing import Any

import solara

from app.page import build_outcome
from app.panels.staleness import use_discard_on_new_run
from sdg1531.engine.indicator import ClassifiedLayer, IndicatorMaps
from sdg1531.engine.land_cover import LandCoverMaps
from sdg1531.enums import IndicatorLayer
from tests.spec_factory import default_spec


@solara.component
def _Probe(run: Any, log: list[str]) -> None:
    use_discard_on_new_run(run, lambda: log.append("discard"))


def test_mounting_is_not_a_run_change():
    """``use_effect`` fires on mount as well as on a change, and at mount a
    panel holds nothing from a previous run by construction.

    It matters more than tidiness for ``MapLayersPanel``: its ``shown``
    reactive is owned by ``page.py`` and outlives the component, so a remount
    that treated the CURRENT run's tiles as stale would pull them off the map
    behind the user's back.
    """
    log: list[str] = []
    _box, rc = solara.render(_Probe(run="run-a", log=log), handle_error=False)
    assert rc is not None

    assert log == []


def test_a_different_run_discards():
    log: list[str] = []
    _box, rc = solara.render(_Probe(run="run-a", log=log), handle_error=False)
    assert rc is not None

    rc.render(_Probe(run="run-b", log=log))

    assert log == ["discard"]


def test_the_same_run_rendered_again_discards_nothing():
    """The floor under the test above: a hook that discarded on every render
    would satisfy it and would also wipe a chart the moment anything else on
    the panel changed."""
    log: list[str] = []
    run = object()
    _box, rc = solara.render(_Probe(run=run, log=log), handle_error=False)
    assert rc is not None

    rc.render(_Probe(run=run, log=log))
    rc.force_update()

    assert log == []


def test_losing_the_run_entirely_counts_as_a_change():
    """``maps`` becomes ``None`` when the spec stops being buildable. Whatever
    is on screen then describes a run that no longer exists, so it goes the
    same way a replaced run does."""
    log: list[str] = []
    _box, rc = solara.render(_Probe(run="run-a", log=log), handle_error=False)
    assert rc is not None

    rc.render(_Probe(run=None, log=log))

    assert log == ["discard"]


def test_the_ee_bearing_dataclasses_compare_by_identity():
    """What keeps every one of these dependency comparisons affordable -- and
    what kept the whole app responsive at all.

    ``ee.ComputedObject.__eq__`` compares ``__dict__``, so a generated
    field-by-field ``__eq__`` walks the whole graph, and an ee graph is a DAG
    whose shared subtrees get re-walked once per path. Reacton compares a
    component's props -- and the closure cells inside them -- with ``==`` on
    every reconciliation, and ``MapLayersPanel`` hands each row a callback
    closed over its ``ClassifiedLayer``. So any spec edit that left one
    layer's graph untouched wedged the kernel mid-render: the map never
    cleared because the render that would have cleared it never finished.

    ``eq=False`` on the three ee-bearing dataclasses is the fix. Asserted as
    "``__eq__`` is object's" rather than by timing a comparison, deliberately:
    under the mutation that reintroduces the defect, a timing test would HANG
    CI rather than fail it.
    """
    for cls in (ClassifiedLayer, IndicatorMaps, LandCoverMaps):
        assert cls.__eq__ is object.__eq__, (
            f"{cls.__name__} carries a generated __eq__, which walks its ee graphs"
        )


def test_two_builds_of_the_same_spec_are_different_runs():
    """The behaviour that identity equality buys, stated positively: rebuilding
    is a new run, and every consumer keyed on ``maps`` reacts to it. That is
    also the RIGHT answer for a reconciliation key -- a rebuild means the
    panels' contents were derived from an object nobody holds any more."""
    spec = default_spec(threshold=0.0)
    first, second = build_outcome(spec).maps, build_outcome(spec).maps

    assert first is not second
    assert first != second


def test_a_threshold_edit_really_does_leave_a_layer_untouched():
    """The precondition that made value equality explode, pinned so the test
    above keeps its reason.

    Threshold is a productivity parameter; the SOC graph does not read it, so
    editing it yields a structurally IDENTICAL soc layer -- the case with no
    early difference to short-circuit on, which is the one that never
    finished. Compared by ``serialize()``, which walks the DAG once (37ms)
    instead of once per path.
    """
    base = default_spec(threshold=0.0)
    before = build_outcome(base).maps
    after = build_outcome(base.evolve(threshold=0.5)).maps
    assert isinstance(before, IndicatorMaps) and isinstance(after, IndicatorMaps)

    soc_before = before.layers()[IndicatorLayer.SOC]
    soc_after = after.layers()[IndicatorLayer.SOC]
    assert soc_before is not soc_after
    assert soc_before.image.serialize() == soc_after.image.serialize()

    # ... while the layer the edit DOES reach differs, so this is a real
    # property of that parameter and not of every comparison.
    assert (
        before.layers()[IndicatorLayer.INDICATOR_15_3_1].image.serialize()
        != after.layers()[IndicatorLayer.INDICATOR_15_3_1].image.serialize()
    )
