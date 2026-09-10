"""Parity stage B: rebuild every scenario and compare the encoded graphs.

Runs offline under the ee fixture in tests/conftest.py. This file must NEVER
import the legacy tree: `component/parameter/directory.py:6-10` mkdirs
`~/module_results` at import, and the whole point of the two stages is that only
stage A (`tools/dump_legacy_graphs.py`, a tool) touches it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import ee
import pytest

from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import build_indicator_maps
from sdg1531.enums import IndicatorLayer
from sdg1531.errors import SpecError
from sdg1531.resolve import resolve
from sdg1531.spec import Compatibility, RunSpec
from tests.parity.expected_divergences import (
    EXPECTED_COMPATIBILITY_DIVERGENCES,
    EXPECTED_DIVERGENCES,
    EXPECTED_LEGACY_AND_PORT_BOTH_FAIL,
    EXPECTED_OFF_GRAPH,
    MODULE_NOTE_CLAIMS,
    matching_entry,
    module_notes,
)
from tools.scenarios import SCENARIOS

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = REPO_ROOT / "tests" / "golden"
METADATA = json.loads((GOLDEN / "metadata.json").read_text())
SCENARIO_DIRS = sorted(p for p in GOLDEN.iterdir() if p.is_dir())


def encode(image: ee.Image) -> str:
    return json.dumps(ee.serializer.encode(image), sort_keys=True)


def test_the_recorded_ee_version_matches_this_environment():
    """Two earthengine-api versions produce different graphs for reasons that have
    nothing to do with the port. Assert this BEFORE comparing any string."""
    assert ee.__version__ == METADATA["ee_version"], (
        f"goldens were recorded against earthengine-api {METADATA['ee_version']}, "
        f"this environment has {ee.__version__}. Do NOT regenerate the goldens: "
        "align the environment, or the parity guarantee is gone."
    )


def test_the_goldens_cover_exactly_the_committed_corpus():
    """Stage B reads spec.json off disk, so a scenario edited in `tools/scenarios.py`
    without re-running stage A would leave `test_scenarios.py` checking one corpus
    and this file checking another, with both green."""
    assert {p.name for p in SCENARIO_DIRS} == set(SCENARIOS)
    drifted = []
    for directory in SCENARIO_DIRS:
        recorded = json.loads((directory / "spec.json").read_text())
        if recorded != SCENARIOS[directory.name].to_dict():
            drifted.append(directory.name)
    assert drifted == [], (
        f"tools/scenarios.py no longer describes the recorded goldens for {drifted}. "
        "Re-run `python -m tools.dump_legacy_graphs` against the LEGACY tree; do not "
        "edit the goldens."
    )


def test_stage_b_never_imports_the_legacy_tree():
    """Importing `component` mkdirs ~/module_results (directory.py:6-10).

    `tests/test_no_side_effects.py` walks `sdg1531` only, so it would NOT catch an
    accidental legacy import here -- this is the check that does. It runs last in
    file order but does not depend on order: every module this file needs is
    already imported by the time any test runs."""
    leaked = sorted(name for name in sys.modules if name.split(".")[0] == "component")
    assert leaked == [], f"the parity suite imported the legacy tree: {leaked}"


def read_spec(directory: Path) -> RunSpec:
    return RunSpec.from_dict(json.loads((directory / "spec.json").read_text()))


def build(directory: Path, *, legacy_compatibility: bool = False):
    spec = read_spec(directory)
    if legacy_compatibility:
        spec = spec.evolve(compatibility=Compatibility())
    resolved = resolve(spec)
    ctx = ExecutionContext.from_aoi_spec(spec.aoi, resolved.analysis_scale)
    return build_indicator_maps(resolved, ctx)


@pytest.mark.parametrize("directory", SCENARIO_DIRS, ids=lambda p: p.name)
def test_scenario_graphs_match_the_goldens(directory):
    """The port, built the way the legacy behaves, must reproduce the legacy graph.

    `legacy_compatibility=True` resets ONLY `spec.compatibility`, whose defaults are
    the legacy behaviour by construction (spec.py). A row that sets a flag describes
    a run the legacy cannot express, so its golden is the graph the flag is off; every
    other axis of that row -- sensor, index, window, land cover, water mask, AOI --
    is still compared exactly as recorded. Resetting the flags is what stops this
    test from having to LICENSE a compatibility difference, which would let a real
    transcription bug hide behind one; `test_compatibility_flags_change_exactly_the_
    recorded_layers` pins what the flags do, separately.
    """
    assert ee.__version__ == METADATA["ee_version"]
    scenario = directory.name

    if scenario in EXPECTED_LEGACY_AND_PORT_BOTH_FAIL:
        # ESA CCI plus a pixel mask that is not the IPCC water code 70. The legacy
        # falls through land_cover.py:56-80 to int(model.seasonality) with that
        # trait still None (TypeError); the port refuses the combination up front
        # with SpecError. Both trees reject it, so there is no graph pair and this
        # is not a divergence.
        assert (directory / "error.json").exists(), (
            f"{scenario} is listed in EXPECTED_LEGACY_AND_PORT_BOTH_FAIL, but stage "
            "A recorded a successful legacy run for it."
        )
        recorded = json.loads((directory / "error.json").read_text())["error"]
        assert recorded.startswith("TypeError"), recorded
        with pytest.raises(SpecError):
            build(directory, legacy_compatibility=True)
        return

    if (directory / "error.json").exists():
        recorded = json.loads((directory / "error.json").read_text())["error"]
        maps = build(directory, legacy_compatibility=True)  # must no longer raise
        assert len(maps.layers()) == 7
        entry = matching_entry(scenario, "*")
        assert entry is not None, (
            f"{scenario} raised {recorded} in the legacy and now succeeds, but no "
            "EXPECTED_DIVERGENCES entry covers it."
        )
        return

    # a diagnostic from an earlier, failing run must not outlive the failure
    for stale in directory.glob("*.actual.json"):
        stale.unlink()

    maps = build(directory, legacy_compatibility=True)
    layers = maps.layers()

    for layer in IndicatorLayer:
        stem = layer.name.lower()
        golden_path = directory / f"{stem}.json"
        assert golden_path.exists(), f"no golden for {scenario}/{stem}"

        golden = json.dumps(json.loads(golden_path.read_text()), sort_keys=True)
        actual = encode(layers[layer].image)
        entry = matching_entry(scenario, stem)

        if actual == golden:
            assert entry is None, (
                f"{scenario}/{stem} matches the golden, but EXPECTED_DIVERGENCES "
                f"still lists {entry[0]} ({entry[1]}). Remove the stale entry."
            )
        elif entry is None:
            # Write the port's own encoding next to the golden so the diff needs no
            # copy-paste. Untracked: .gitignore holds the pattern. Written ONLY on
            # an unlicensed divergence -- writing it for a licensed one too would
            # leave a diagnostic behind on every green run, and "no .actual.json
            # files" is exactly the signal that the harness has converged.
            actual_path = directory / f"{stem}.actual.json"
            actual_path.write_text(json.dumps(json.loads(actual), indent=2, sort_keys=True))
            raise AssertionError(
                f"{scenario}/{stem} diverges from the legacy graph and no "
                f"EXPECTED_DIVERGENCES entry covers it. The port's encoding was "
                f"written to {actual_path} for the diff. Phase 1 is a "
                "transcription: either restore the legacy shape or record the "
                "divergence with a reason."
            )


@pytest.mark.parametrize("directory", SCENARIO_DIRS, ids=lambda p: p.name)
def test_compatibility_flags_change_exactly_the_recorded_layers(directory):
    """What the corpus's non-default Compatibility flags actually move.

    This is deliberately a PORT-vs-PORT comparison -- the same spec with the flags
    on and off -- and it makes no parity claim: `Compatibility`'s defaults are the
    legacy behaviour, so the flags-off side is the one `test_scenario_graphs_match_
    the_goldens` anchors against the legacy goldens. Its job is the other half: to
    prove the flags are not inert, and to pin their footprint in both directions so
    that a flag which starts or stops moving a layer fails here rather than being
    absorbed into a licence.
    """
    scenario = directory.name
    expected = EXPECTED_COMPATIBILITY_DIVERGENCES.get(scenario, frozenset())

    if scenario in EXPECTED_LEGACY_AND_PORT_BOTH_FAIL:
        assert expected == frozenset(), (
            f"{scenario} is refused before any graph is built; it cannot have a "
            "compatibility footprint."
        )
        return

    if read_spec(directory).compatibility == Compatibility():
        assert expected == frozenset(), (
            f"{scenario} carries the default Compatibility, so nothing can move."
        )
        return

    as_recorded = build(directory).layers()
    legacy_default = build(directory, legacy_compatibility=True).layers()
    moved = {
        layer.name.lower()
        for layer in IndicatorLayer
        if encode(as_recorded[layer].image) != encode(legacy_default[layer].image)
    }
    assert moved == set(expected), (
        f"{scenario}'s compatibility flags move {sorted(moved)}, but the register "
        f"records {sorted(expected)}."
    )


def test_every_compatibility_footprint_names_a_scenario_that_sets_a_flag():
    """The other direction: an entry for a scenario with default flags is a typo."""
    default = Compatibility()
    stray = sorted(
        name
        for name in EXPECTED_COMPATIBILITY_DIVERGENCES
        if read_spec(GOLDEN / name).compatibility == default
    )
    assert stray == [], f"compatibility footprints for scenarios that set no flag: {stray}"


def test_every_divergence_entry_matches_at_least_one_pair():
    stems = [layer.name.lower() for layer in IndicatorLayer]
    unused = []
    for key in EXPECTED_DIVERGENCES:
        hit = any(
            matching_entry(directory.name, stem) == (key, EXPECTED_DIVERGENCES[key])
            for directory in SCENARIO_DIRS
            for stem in stems
        )
        if not hit:
            unused.append(key)
    assert not unused, f"EXPECTED_DIVERGENCES entries match nothing: {unused}"


def test_every_off_graph_divergence_names_a_test_that_exists():
    tests_root = Path(__file__).parent.parent
    sources = "\n".join(path.read_text() for path in tests_root.rglob("test_*.py"))
    for key, entry in EXPECTED_OFF_GRAPH.items():
        assert f"def {entry['test']}" in sources, (
            f"off-graph divergence {key!r} names {entry['test']}, which no test defines"
        )


def test_every_module_divergence_note_is_claimed_by_the_register():
    """Every numbered EXPECTED_DIVERGENCES note in the port has a register entry.

    This is the direction that stops a new licence being granted in a docstring and
    never reaching the harness."""
    unclaimed = sorted(set(module_notes(REPO_ROOT)) - set(MODULE_NOTE_CLAIMS))
    assert unclaimed == [], (
        f"module EXPECTED_DIVERGENCES notes with no register entry: {unclaimed}. Add "
        "one to EXPECTED_DIVERGENCES (with its GRAPH_DIVERGENCE_NOTES key) or to "
        "EXPECTED_OFF_GRAPH."
    )


def test_every_register_note_reference_names_a_real_module_note():
    """And the other direction: a register entry cannot cite a note that is gone."""
    dangling = sorted(set(MODULE_NOTE_CLAIMS) - set(module_notes(REPO_ROOT)))
    assert dangling == [], f"register entries citing notes that no longer exist: {dangling}"


def test_every_note_claim_names_a_register_entry_that_is_there():
    graph_keys = {f"graph:{s}/{layer}" for s, layer in EXPECTED_DIVERGENCES}
    off_graph_keys = {f"off_graph:{key}" for key in EXPECTED_OFF_GRAPH}
    known = graph_keys | off_graph_keys
    missing = sorted(claim for claim in MODULE_NOTE_CLAIMS.values() if claim not in known)
    assert missing == [], f"note claims pointing at no register entry: {missing}"
