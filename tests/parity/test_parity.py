"""Parity stage B: rebuild every scenario and compare the encoded graphs.

Runs offline under the ee fixture in tests/conftest.py. This file must NEVER
import the legacy tree: `component/parameter/directory.py:6-10` mkdirs
`~/module_results` at import, and the whole point of the two stages is that only
stage A (`tools/dump_legacy_graphs.py`, a tool) touches it.

Graphs are compared through `tests/parity/canonical.py`, not as raw serialized
strings. `ee` numbers its scope keys in traversal order, so the port's one extra
`Image.rename` on the indicator layer shifted every later key and made the raw
strings differ in almost every line -- which is how that layer came to carry a
corpus-wide LICENCE covering its entire graph. The canonical form is independent
of that numbering, so the rename can be spliced out as a named normalisation and
everything else compared byte for byte.
"""

from __future__ import annotations

import difflib
import importlib
import json
import re
import sys
from pathlib import Path

import ee
import pytest

from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps, build_indicator_maps
from sdg1531.enums import IndicatorLayer
from sdg1531.errors import SpecError
from sdg1531.resolve import resolve
from sdg1531.spec import Compatibility, RunSpec
from tests.ee_offline import fixture_provenance
from tests.parity import canonical
from tests.parity.canonical import render, strip_indicator_band_rename
from tests.parity.expected_divergences import (
    EXPECTED_COMPATIBILITY_DIVERGENCES,
    EXPECTED_DIVERGENCES,
    EXPECTED_LEGACY_AND_PORT_BOTH_FAIL,
    EXPECTED_LEGACY_ONLY_FAILS,
    EXPECTED_NORMALISATIONS,
    EXPECTED_OFF_GRAPH,
    HELD_CONSTANT,
    MODULE_NOTE_CLAIMS,
    matching_entry,
    module_notes,
)
from tools.scenarios import SCENARIOS

REPO_ROOT = Path(__file__).resolve().parents[2]
# Tier 4. Declared in pyproject.toml and, until fix round 2, applied to nothing: a
# CI job running `pytest -m parity` selected zero tests. Module-level so a new test
# in this file cannot miss it, and `test_every_parity_module_carries_the_marker`
# checks the whole directory.
pytestmark = pytest.mark.parity

GOLDEN = REPO_ROOT / "tests" / "golden"
METADATA = json.loads((GOLDEN / "metadata.json").read_text())
SCENARIO_DIRS = sorted(p for p in GOLDEN.iterdir() if p.is_dir())

# how much of the legacy-vs-port diff to put in a failing assertion. The whole
# encoding runs to thousands of lines; the first differing nodes are the answer.
_DIFF_LINES = 40


def encode(image: ee.Image) -> str:
    return json.dumps(ee.serializer.encode(image), sort_keys=True)


def graph_diff(golden: str, actual: str) -> str:
    """The first `_DIFF_LINES` lines of the canonical legacy-vs-port diff."""
    lines = list(
        difflib.unified_diff(
            golden.splitlines(), actual.splitlines(), "legacy", "port", lineterm="", n=1
        )
    )
    head = "\n".join(lines[:_DIFF_LINES])
    return head if len(lines) <= _DIFF_LINES else f"{head}\n... {len(lines) - _DIFF_LINES} more"


def test_the_recorded_ee_version_matches_this_environment() -> None:
    """Two earthengine-api versions produce different graphs for reasons that have
    nothing to do with the port. Assert this BEFORE comparing any string."""
    assert ee.__version__ == METADATA["ee_version"], (
        f"goldens were recorded against earthengine-api {METADATA['ee_version']}, "
        f"this environment has {ee.__version__}. Do NOT regenerate the goldens: "
        "align the environment, or the parity guarantee is gone."
    )


def test_the_recorded_algorithm_table_is_the_one_this_environment_installs() -> None:
    """The second half of the R6 guard, and it was recorded but never checked.

    `ee_version` alone does not pin the graphs: the ALGORITHM SIGNATURES decide
    argument names and value promotion during client-side serialization, so a
    stage-A run against a live discovery document produces different encodings from
    one against the committed fixture, at the same `ee` version. Asserted here for
    the same reason and in the same place -- before any comparison.

    What this does NOT catch is the fixture being regenerated with different
    contents at the same `ee` version: `metadata.json` records a provenance string,
    not a digest, and recording a digest would mean re-running stage A.
    """
    assert METADATA["algorithms"] == fixture_provenance(), (
        f"goldens were recorded against algorithm table {METADATA['algorithms']!r}, "
        f"this environment installs {fixture_provenance()!r}. Do NOT regenerate the "
        "goldens: align the environment."
    )


def test_the_goldens_cover_exactly_the_committed_corpus() -> None:
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


def test_stage_b_never_imports_the_legacy_tree() -> None:
    """Importing `component` mkdirs ~/module_results (directory.py:6-10).

    `tests/test_no_side_effects.py` walks `sdg1531` only, so it would NOT catch an
    accidental legacy import here -- this is the check that does, and it catches the
    case that matters whatever order it runs in, because every module-level import
    in this file has happened before any test body does. What it cannot see is a
    LAZY `import component` inside a test function defined after it; nothing in this
    suite does that, and the fix if one ever appears is to hoist the import, not to
    move this test."""
    leaked = sorted(name for name in sys.modules if name.split(".")[0] == "component")
    assert leaked == [], f"the parity suite imported the legacy tree: {leaked}"


def read_spec(directory: Path) -> RunSpec:
    return RunSpec.from_dict(json.loads((directory / "spec.json").read_text()))


def build(directory: Path, *, legacy_compatibility: bool = False) -> IndicatorMaps:
    spec = read_spec(directory)
    if legacy_compatibility:
        spec = spec.evolve(compatibility=Compatibility())
    resolved = resolve(spec)
    ctx = ExecutionContext.from_aoi_spec(spec.aoi, resolved.analysis_scale)
    return build_indicator_maps(resolved, ctx)


@pytest.mark.parametrize("directory", SCENARIO_DIRS, ids=lambda p: p.name)
def test_scenario_graphs_match_the_goldens(directory: Path) -> None:
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
        # A custom land cover source with a JRC or asset-band mask: the legacy
        # raised before building anything, so stage A recorded no layer files and
        # there is no pair to compare. Membership of a SET, not a ("sNN", "*") glob
        # in EXPECTED_DIVERGENCES -- a glob says "every layer of this scenario may
        # differ", which is not what is meant and would become a real licence the
        # moment a re-run of stage A recorded graphs for one of these.
        recorded = json.loads((directory / "error.json").read_text())["error"]
        assert scenario in EXPECTED_LEGACY_ONLY_FAILS, (
            f"{scenario} raised {recorded} in the legacy, but no register entry covers it."
        )
        maps = build(directory, legacy_compatibility=True)  # must no longer raise
        assert len(maps.layers()) == 7
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

        golden_graph = json.loads(golden_path.read_text())
        actual_graph = ee.serializer.encode(layers[layer].image)

        if layer is IndicatorLayer.INDICATOR_15_3_1:
            # EXPECTED_NORMALISATIONS["indicator_band_rename"]. Both asserts are
            # load-bearing: the splice has to fire on the port (or the port has
            # stopped renaming, or moved the node the goldens pin) and has to
            # DECLINE on the legacy (or it is cancelling the same node on both
            # sides, which would compare nothing at all).
            actual_graph, spliced = strip_indicator_band_rename(actual_graph)
            assert spliced, (
                f"{scenario}/{stem}: the port no longer ends "
                "Image.uint8 <- Image.where <- Image.rename(['indicator_15_3_1']), "
                "so the normalisation could not fire. Either the rename is gone or "
                "the cast or water mask moved -- both are graph changes the goldens "
                "pin. See EXPECTED_NORMALISATIONS."
            )
            golden_graph, golden_spliced = strip_indicator_band_rename(golden_graph)
            assert not golden_spliced, (
                f"{scenario}/{stem}: the LEGACY golden carries the rename too, so "
                "the normalisation is subtracting the same node from both sides and "
                "proving nothing. run_15_3_1.py:411 renames nothing; a golden that "
                "does was not recorded from the legacy."
            )

        golden = render(golden_graph)
        actual = render(actual_graph)
        entry = matching_entry(scenario, stem)

        if actual == golden:
            assert entry is None, (
                f"{scenario}/{stem} matches the golden, but EXPECTED_DIVERGENCES "
                f"still lists {entry[0]} ({entry[1]}). Remove the stale entry."
            )
        elif entry is None:
            # Write the port's canonical graph next to the golden. Untracked:
            # .gitignore holds the pattern. Written ONLY on an unlicensed
            # divergence -- writing it for a licensed one too would leave a
            # diagnostic behind on every green run, and "no .actual.json files" is
            # exactly the signal that the harness has converged.
            actual_path = directory / f"{stem}.actual.json"
            actual_path.write_text(actual)
            raise AssertionError(
                f"{scenario}/{stem} diverges from the legacy graph and no "
                f"EXPECTED_DIVERGENCES entry covers it. Phase 1 is a transcription: "
                "either restore the legacy shape or record the divergence with a "
                f"reason.\nThe port's canonical graph is at {actual_path}.\n"
                f"{graph_diff(golden, actual)}"
            )


@pytest.mark.parametrize("directory", SCENARIO_DIRS, ids=lambda p: p.name)
def test_compatibility_flags_change_exactly_the_recorded_layers(directory: Path) -> None:
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


def test_every_compatibility_footprint_names_a_scenario_that_sets_a_flag() -> None:
    """The other direction: an entry for a scenario with default flags is a typo."""
    default = Compatibility()
    stray = sorted(
        name
        for name in EXPECTED_COMPATIBILITY_DIVERGENCES
        if read_spec(GOLDEN / name).compatibility == default
    )
    assert stray == [], f"compatibility footprints for scenarios that set no flag: {stray}"


def test_every_divergence_entry_matches_at_least_one_pair() -> None:
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


def test_every_parity_module_carries_the_marker() -> None:
    """`pyproject.toml` declares a `parity` marker for Task 18's CI to select on.

    It was declared and applied to nothing, so `pytest -m parity` selected zero
    tests. That is not silent -- pytest exits 5, "no tests collected" -- but a job
    that tolerates 5, or that later selects a wider expression, gets a green run
    proving nothing, and the marker is exactly the thing Task 18 will select on.

    Checked against each module's `pytestmark` ATTRIBUTE, which is what pytest
    itself reads, rather than by grepping the source for the assignment. This test
    lives in a marked module, so `-m parity` selects it, and it is what catches a
    new parity file that forgets the mark.
    """
    unmarked = []
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        module = importlib.import_module(f"tests.parity.{path.stem}")
        marks = getattr(module, "pytestmark", [])
        marks = marks if isinstance(marks, list) else [marks]
        if not any(mark.name == "parity" for mark in marks):
            unmarked.append(path.name)
    assert unmarked == [], (
        f"parity modules with no `pytestmark = pytest.mark.parity`: {unmarked}. "
        "Without it `pytest -m parity` silently skips them."
    )


def test_no_layer_is_licensed() -> None:
    """The strongest statement the register can make, and it is currently true.

    Every one of the 112 graph pairs is compared byte for byte after
    canonicalisation, with nothing exempted. This is a tripwire, not a law: if a
    graph difference ever genuinely needs licensing, delete this test in the same
    change, deliberately, so the decision is visible in the diff. Reach for
    EXPECTED_NORMALISATIONS first -- a splice compares the rest of the layer, a
    licence compares none of it.
    """
    assert EXPECTED_DIVERGENCES == {}


def test_every_legacy_only_failure_recorded_a_legacy_crash() -> None:
    """The other direction on EXPECTED_LEGACY_ONLY_FAILS: a scenario listed there
    whose golden holds real layer graphs would be a stale entry hiding a comparison
    that could now be made."""
    wrong = sorted(
        name for name in EXPECTED_LEGACY_ONLY_FAILS if not (GOLDEN / name / "error.json").exists()
    )
    assert wrong == [], (
        f"listed as legacy-only failures but stage A recorded a successful run: {wrong}"
    )


def test_the_two_failure_sets_do_not_overlap() -> None:
    """A scenario is either refused by both trees or only by the legacy. Listing one
    in both would make whichever branch runs first silently decide the other's."""
    overlap = EXPECTED_LEGACY_ONLY_FAILS & EXPECTED_LEGACY_AND_PORT_BOTH_FAIL

    assert overlap == frozenset(), f"listed in both failure registers: {sorted(overlap)}"


def _defines(name: str, sources: str) -> bool:
    """Whether `sources` defines a test called exactly `name`.

    A plain `f"def {name}"` substring is a PREFIX match: a test renamed from
    `test_foo` to `test_foo_and_something_else` would keep satisfying an entry that
    names `test_foo`. The trailing `(` is the word boundary.
    """
    return re.search(rf"^\s*(?:async )?def {re.escape(name)}\(", sources, re.MULTILINE) is not None


def _test_sources() -> str:
    tests_root = Path(__file__).parent.parent
    return "\n".join(path.read_text() for path in tests_root.rglob("test_*.py"))


def test_every_off_graph_divergence_names_tests_that_exist() -> None:
    """Each entry names EVERY test that pins it, not one of them.

    Two entries used to name a single test for a two-part claim -- `unrecognised_arm`
    cited the water-mask test for a land-cover-or-water-mask claim, and
    `unresolved_period_bound` cited the trend test for a trend/state/performance one
    -- so the register read as coverage it did not have. Tuples make the whole claim
    accountable.
    """
    sources = _test_sources()
    for key, entry in EXPECTED_OFF_GRAPH.items():
        assert entry["tests"], f"off-graph divergence {key!r} names no test at all"
        for name in entry["tests"]:
            assert _defines(name, sources), (
                f"off-graph divergence {key!r} names {name}, which no test defines"
            )


def test_every_held_constant_entry_names_tests_that_exist() -> None:
    """A held-constant entry is a claim that something IS pinned somewhere, just not
    by the graph comparison. If the tests it names are gone, so is the pin."""
    sources = _test_sources()
    for key, entry in HELD_CONSTANT.items():
        assert entry["tests"], f"held-constant entry {key!r} names no test at all"
        for name in entry["tests"]:
            assert _defines(name, sources), (
                f"held-constant entry {key!r} names {name}, which no test defines"
            )


def test_every_normalisation_names_a_splice_and_tests_that_exist() -> None:
    """A normalisation is a claim about CODE, so both halves have to be real: the
    function that performs the splice and the tests that pin what it refuses."""
    sources = _test_sources()
    for key, entry in EXPECTED_NORMALISATIONS.items():
        assert hasattr(canonical, entry["splice"]), (
            f"normalisation {key!r} names {entry['splice']}, which "
            "tests/parity/canonical.py does not define"
        )
        for name in entry["tests"]:
            assert _defines(name, sources), (
                f"normalisation {key!r} names {name}, which no test defines"
            )


def test_every_module_divergence_note_is_claimed_by_the_register() -> None:
    """Every numbered EXPECTED_DIVERGENCES note in the port has a register entry.

    This is the direction that stops a new licence being granted in a docstring and
    never reaching the harness."""
    unclaimed = sorted(set(module_notes(REPO_ROOT)) - set(MODULE_NOTE_CLAIMS))
    assert unclaimed == [], (
        f"module EXPECTED_DIVERGENCES notes with no register entry: {unclaimed}. Add "
        "one to EXPECTED_OFF_GRAPH, to EXPECTED_NORMALISATIONS, or -- last resort -- "
        "to EXPECTED_DIVERGENCES with its GRAPH_DIVERGENCE_NOTES key. The roster is "
        "SCANNED off sdg1531/, so a note in a newly written module reaches this test "
        "on its own."
    )


def test_every_register_note_reference_names_a_real_module_note() -> None:
    """And the other direction: a register entry cannot cite a note that is gone."""
    dangling = sorted(set(MODULE_NOTE_CLAIMS) - set(module_notes(REPO_ROOT)))
    assert dangling == [], f"register entries citing notes that no longer exist: {dangling}"


def test_every_note_claim_names_a_register_entry_that_is_there() -> None:
    known = (
        {f"graph:{s}/{layer}" for s, layer in EXPECTED_DIVERGENCES}
        | {"legacy_only_fails"}
        | {f"normalised:{key}" for key in EXPECTED_NORMALISATIONS}
        | {f"off_graph:{key}" for key in EXPECTED_OFF_GRAPH}
    )
    missing = sorted(claim for claim in MODULE_NOTE_CLAIMS.values() if claim not in known)
    assert missing == [], f"note claims pointing at no register entry: {missing}"
