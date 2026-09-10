"""The corpus is a reduction, so assert what it actually covers."""

from itertools import product

import pytest

from sdg1531.spec import CustomLandCoverSource, RunSpec
from tools.scenarios import AXES, SCENARIOS, axis_levels

# Tier 4. Declared in pyproject.toml and, until fix round 2, applied to nothing: a
# CI job running `pytest -m parity` selected zero tests. Module-level so a new test
# in this file cannot miss it, and `test_every_parity_module_carries_the_marker`
# checks the whole directory.
pytestmark = pytest.mark.parity


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


def test_sensor_by_index_is_covered_exhaustively() -> None:
    pairs = {(axis_levels(name)["sensor"], axis_levels(name)["index"]) for name in SCENARIOS}
    assert pairs == set(product(AXES["sensor"], AXES["index"]))


def test_land_cover_by_water_mask_is_covered_exhaustively() -> None:
    pairs = {(axis_levels(name)["land_cover"], axis_levels(name)["water"]) for name in SCENARIOS}
    assert pairs == set(product(AXES["land_cover"], AXES["water"]))


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_scenario_round_trips_through_json(name: str) -> None:
    spec = SCENARIOS[name]
    assert RunSpec.from_dict(spec.to_dict()) == spec


def test_scenario_fingerprints_are_all_distinct() -> None:
    fingerprints = {name: SCENARIOS[name].fingerprint() for name in SCENARIOS}
    assert len(set(fingerprints.values())) == len(fingerprints)
