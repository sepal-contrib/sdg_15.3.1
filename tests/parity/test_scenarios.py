"""The corpus is a reduction, so assert what it actually covers.

Two different claims live here and they are not interchangeable. A test over
``SCENARIOS`` measures the TABLE: what ``tools/scenarios.py`` says the corpus asks
for. A test over :func:`compared_scenarios` measures the PROOF: the rows that
actually yield a legacy-vs-port graph pair. Twelve of the 28 rows record a legacy
crash instead of a graph, so the two answers differ, and a coverage claim phrased
over the table reads as a statement about parity coverage while measuring only
the thing it was derived from.
"""

from itertools import product
from pathlib import Path

import pytest

from sdg1531.spec import CustomLandCoverSource, RunSpec
from tools.scenarios import AXES, SCENARIOS, axis_levels

# Tier 4. Declared in pyproject.toml and, until fix round 2, applied to nothing: a
# CI job running `pytest -m parity` selected zero tests. Module-level so a new test
# in this file cannot miss it, and `test_every_parity_module_carries_the_marker`
# checks the whole directory.
pytestmark = pytest.mark.parity

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden"


def compared_scenarios() -> tuple[str, ...]:
    """The rows stage B actually compares a graph pair for.

    Read off the goldens, the way ``test_scenario_graphs_match_the_goldens``
    reads them: a scenario directory holding ``error.json`` recorded a legacy
    crash, so stage A wrote no layer graphs and there is nothing to compare.
    Derived rather than listed, so a re-run of stage A that stops one of them
    crashing moves this set on its own.
    """
    return tuple(name for name in SCENARIOS if not (GOLDEN / name / "error.json").exists())


def test_the_corpus_has_28_uniquely_named_scenarios() -> None:
    assert len(SCENARIOS) == 28


def test_the_custom_land_cover_arm_carries_a_genuinely_custom_scheme() -> None:
    """LandCoverScheme.default() has is_custom=False. If custom_full used it, the
    custom_full and custom_half rows would exercise the same code path and the
    half-custom defect would go untested."""
    full = SCENARIOS["s05"].land_cover
    half = SCENARIOS["s09"].land_cover
    # LandCoverSource is a union and only the custom arm carries `.scheme`, so
    # narrowing it here also pins that these two rows ARE the custom arm -- which
    # is the premise the rest of the assertion rests on.
    assert isinstance(full, CustomLandCoverSource)
    assert isinstance(half, CustomLandCoverSource)

    assert full.scheme is not None
    assert full.scheme.is_custom is True
    assert half.scheme is None


def test_every_scenario_sets_a_vi_threshold() -> None:
    """integration.py:410-415 reaches `img.gt(threshold)` on five of the six VI
    rungs, and the port narrows the field with require_float. A corpus that left
    spec.threshold at its None default would make every one of those rungs raise
    SpecError in the port while the legacy built a graph -- 24 of the 28 rows
    would become whole-scenario divergences and compare nothing."""
    unset = [name for name, spec in SCENARIOS.items() if spec.threshold is None]
    assert unset == [], unset


def test_every_level_of_every_axis_appears_at_least_once() -> None:
    seen: dict[str, set[str]] = {axis: set() for axis in AXES}
    for name in SCENARIOS:
        for axis, level in axis_levels(name).items():
            seen[axis].add(level)
    for axis, levels in AXES.items():
        assert seen[axis] == set(levels), f"{axis} is not fully covered"


def test_every_scenario_names_a_level_on_every_axis() -> None:
    """A stray column reads as coverage but is never applied.

    _build() indexes every axis by name, so a row that OMITS one already fails
    loudly at import. A row that carries an EXTRA key -- a misspelling sitting
    beside the real column, say -- is silently ignored by _build and counted as a
    level by nothing, which is what this catches."""
    for name in SCENARIOS:
        assert set(axis_levels(name)) == set(AXES), name


def test_the_table_asks_for_every_sensor_by_index_pair() -> None:
    """A claim about the TABLE, and its name now says so.

    It was called `test_sensor_by_index_is_covered_exhaustively`, which reads as a
    statement about parity coverage while measuring the table it is derived from --
    and under that name seven of the eighteen pairs turned out to reach no compared
    scenario at all, `(sentinel2, msvi)` and `(landsat_pair, msvi)` among them, so
    `engine.integration._calculate_msvi` was verified by nothing. What the pairs
    actually prove is
    `test_every_axis_level_reaches_a_scenario_that_is_compared`'s business.
    """
    pairs = {(axis_levels(name)["sensor"], axis_levels(name)["index"]) for name in SCENARIOS}
    assert pairs == set(product(AXES["sensor"], AXES["index"]))


def test_the_table_asks_for_every_land_cover_by_water_mask_pair() -> None:
    """The same kind of claim, about the same kind of table. Unlike sensor x index,
    the pairs this one asks for that no comparison reaches are fully accounted for:
    they are exactly EXPECTED_LEGACY_ONLY_FAILS and
    EXPECTED_LEGACY_AND_PORT_BOTH_FAIL, both of which the register explains."""
    pairs = {(axis_levels(name)["land_cover"], axis_levels(name)["water"]) for name in SCENARIOS}
    assert pairs == set(product(AXES["land_cover"], AXES["water"]))


def test_the_compared_subset_is_a_real_and_proper_subset() -> None:
    """The premise the coverage test below rests on.

    If `compared_scenarios()` ever returned everything, the test below would say
    exactly what the table-level ones already say and quietly stop being a second
    measurement; if it returned nothing, it would pass by having no levels to check.
    """
    compared = set(compared_scenarios())

    assert compared, "no scenario compares a graph pair; the corpus proves nothing"
    assert compared < set(SCENARIOS), (
        "every scenario compares a graph pair, so this is no longer a second "
        "measurement -- if stage A really did stop crashing, the register's "
        "EXPECTED_LEGACY_ONLY_FAILS entries are stale too."
    )


def test_every_axis_level_reaches_a_scenario_that_is_compared() -> None:
    """Coverage over the rows that yield a graph pair, not over the table.

    `test_every_level_of_every_axis_appears_at_least_once` is satisfied by a level
    that appears only on rows the legacy refused to build -- those rows compare
    nothing, so the level is asked for and never proved. This is the same claim
    made where it counts.
    """
    seen: dict[str, set[str]] = {axis: set() for axis in AXES}
    for name in compared_scenarios():
        for axis, level in axis_levels(name).items():
            seen[axis].add(level)

    unproven = {
        axis: sorted(set(levels) - seen[axis])
        for axis, levels in AXES.items()
        if set(levels) - seen[axis]
    }
    assert unproven == {}, (
        f"axis levels no compared scenario reaches: {unproven}. Every row carrying "
        "them records a legacy crash, so nothing about them is compared against the "
        "legacy at all."
    )


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_scenario_round_trips_through_json(name: str) -> None:
    spec = SCENARIOS[name]
    assert RunSpec.from_dict(spec.to_dict()) == spec


def test_scenario_fingerprints_are_all_distinct() -> None:
    fingerprints = {name: SCENARIOS[name].fingerprint() for name in SCENARIOS}
    assert len(set(fingerprints.values())) == len(fingerprints)
