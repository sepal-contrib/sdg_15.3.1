"""Soil organic carbon. Transcribed from component/scripts/soil_organic_carbon.py:6-178.

The interesting fact under test is D13: the first year pair is encoded at scale 100
(:50) and every later pair at scale 10 (:114), so from year two onward the codes fall
outside IPCC_TRANSITION_CODES entirely and every CHANGED pixel loses its stock update.
Phase 1 preserves this byte-for-byte behind
``Compatibility.soc_subsequent_transition_scale``.

Two habits this file keeps to, both because a count over an `ee` graph is a
POST-CSE distinct-node count and cannot see a duplicated operation:

* the transition scales are read as a ``{(year, year+1): scale}`` MAP keyed by the
  ``calendarRange`` windows under each operand, not counted -- the map says which
  pair got which scale, which is the whole of D13;
* where a count is unavoidable it is stated as ``BLOCKS`` / ``LOOP_YEARS``,
  derived from the period below and checked against the graph.

The stub `ResolvedSpec` (tests/engine/conftest.py) is used for the shape tests with
SOC years deliberately unlike its own 2001/2015 land-cover defaults, so a builder
reading `lc_year_*_esa` instead of the SOC fields lands different windows. The two
clamping tests at the bottom run the real `resolve()`, which is the only thing that
can show the start year arriving unclamped while the end year is clamped.
"""

from __future__ import annotations

from dataclasses import replace

import ee
import pytest

from sdg1531.catalog import ASSETS, INT16_MIN, LAND_COVER_FIRST_YEAR, LAND_COVER_MAX_YEAR
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.soc import (
    build_soil_organic_carbon,
    climate_coefficient,
    soc_transition_code,
)
from sdg1531.errors import SpecError
from sdg1531.resolve import resolve
from sdg1531.spec import Compatibility, FixedClimate, PeriodOverride, PerPixelClimate
from sdg1531.tables import (
    C_CONVERSION_FACTOR,
    CLIMATE_CONVERSION_MATRIX,
    INPUT_FACTOR,
    IPCC_TRANSITION_CODES,
    MANAGEMENT_FACTOR,
    TRANSLATION_MATRIX,
)
from tests.engine.conftest import make_resolved
from tests.engine.graph import (
    _calendar_windows,
    _call,
    _image_constant,
    _loaded_asset_ids,
    _root,
    _scalar_list_arg,
    _spine,
    _walk,
)
from tests.spec_factory import DEFAULT_PERIODS, default_spec

# Distinct, non-degenerate, and unlike conftest's 2001/2015 land-cover defaults.
SOC_START = 1996
SOC_END = 2003

# soil_organic_carbon.py:95 -- `range(start + 1, end)`. The pairs are therefore
# (start, start+1) from the first block and (y, y+1) for y in LOOP_YEARS.
LOOP_YEARS = range(SOC_START + 1, SOC_END)
# One first block (:29-89) plus one per loop iteration (:95-157). Every per-block
# node hangs off `lc_transition`, which is re-wrapped each pass, so the blocks are
# structurally distinct and CSE cannot collapse them.
BLOCKS = 1 + len(LOOP_YEARS)

# The argument each node on THIS module's chains carries its receiver in, verified
# against the encoder. Passed to the shared spine walker; the other engine test
# files keep their own tables, which list different functions.
_RECEIVER_ARG = {
    "Image.uint8": "value",
    "Image.rename": "input",
    "Image.where": "input",
    "Image.remap": "image",
    "Image.clip": "input",
    "Image.updateMask": "image",
}

_COMPARISONS = ("Image.eq", "Image.neq", "Image.lt", "Image.lte", "Image.gt", "Image.gte")


def soc_image(**overrides):
    """The SOC band for a stub resolved spec, with the SOC years set explicitly."""
    years = {"soc_year_start": SOC_START, "soc_year_end_esa": SOC_END}
    r = make_resolved(**{**years, **overrides})
    return build_soil_organic_carbon(r, aoi_context())


def aoi_context():
    return ExecutionContext.from_feature_collection(ee.FeatureCollection("users/test/aoi"), 250)


# --- graph helpers ------------------------------------------------------------


def comparison(node, deref):
    """`(function name, constant)` for a comparison of an image against a constant.

    `None` when `node` is not a comparison at all, and a constant of `None` when the
    right-hand side is another image (`lc_time0.neq(lc_time1)`) rather than a scalar.
    """
    call = _call(node)
    if call is None or call.get("functionName") not in _COMPARISONS:
        return None
    return call["functionName"], _image_constant(deref(call["arguments"]["image2"]), deref)


def year_of(node, deref, graph):
    """The year of the single degenerate `calendarRange(y, y, "year")` under `node`.

    Each `lc_time*` chain also carries the collection-wide `calendarRange(start, end)`
    from :15-17, which is why only the degenerate window is taken. Raises rather than
    returning None: a year that silently came back empty would make the transition-code
    map below agree with itself.
    """
    windows = {w for w in _calendar_windows(node, deref, graph) if w[0] == w[1]}
    if len(windows) != 1:
        raise AssertionError(f"expected one degenerate calendarRange, found {sorted(windows)}")
    return windows.pop()[0]


def transition_scales(image):
    """`{(lc0 year, lc1 year): scale}` for every `lc0.multiply(k).add(lc1)` node.

    This is the D13 assertion's whole substance: it reads the scale off each pair
    together with the two years that pair came from, so it says WHICH pair got which
    multiplier. A count could not -- and the percent-change `multiply(100)` at :164
    is excluded structurally, because its parent is the `where` ladder, not an
    `Image.add`.
    """
    deref, graph, root = _root(image)
    scales = {}
    for node in _walk(root, deref, graph):
        add = _call(node)
        if add is None or add.get("functionName") != "Image.add":
            continue
        multiply = _call(deref(add["arguments"]["image1"]))
        if multiply is None or multiply.get("functionName") != "Image.multiply":
            continue
        scale = _image_constant(deref(multiply["arguments"]["image2"]), deref)
        if scale is None:  # `lc_transition_time.add(ee.Image(1))` at :109
            continue
        lc0 = deref(multiply["arguments"]["image1"])
        lc1 = deref(add["arguments"]["image2"])
        scales[(year_of(lc0, deref, graph), year_of(lc1, deref, graph))] = scale
    return scales


def select_indices(image):
    """The SET of band indices passed to `.select(...)` anywhere in the graph.

    A population, with no multiplicity and no idea which site contributed what: two
    sites reading `soc_images.select(year_index)` mean shifting either one alone
    leaves this set unchanged. Good only for "nothing ELSE is selected"; the
    per-site indices are `stack_terms()`'s job.
    """
    deref, graph, root = _root(image)
    indices = set()
    for node in _walk(root, deref, graph):
        call = _call(node)
        if call is None or call.get("functionName") != "Image.select":
            continue
        indices.update(_scalar_list_arg(deref(call["arguments"]["bandSelectors"]), deref))
    return indices


def band_index(node, deref):
    """The single band index of an `Image.select` node."""
    call = _call(deref(node))
    assert call is not None and call.get("functionName") == "Image.select", call
    selectors = _scalar_list_arg(deref(call["arguments"]["bandSelectors"]), deref)
    assert len(selectors) == 1, selectors
    return selectors[0]


def soc_stack(image):
    """The `soc_images` `addBands` chain, base first (:89, :157).

    `a.addBands(b).addBands(c)` nests as `addBands(addBands(a, b), c)`, so the chain
    is walked through `dstImg` and reversed. `lc_images` is accumulated but never
    referenced, so it is never serialized and the longest chain in the graph is
    `soc_images`' -- which is itself the check that `lc_images` stayed dead.
    """
    deref, graph, root = _root(image)

    def chain(node):
        bands, current = [], deref(node)
        while (call := _call(current)) is not None and call.get("functionName") == "Image.addBands":
            bands.append(deref(call["arguments"]["srcImg"]))
            current = deref(call["arguments"]["dstImg"])
        bands.append(current)
        return list(reversed(bands))

    chains = [
        chain(node)
        for node in _walk(root, deref, graph)
        if (call := _call(node)) is not None and call.get("functionName") == "Image.addBands"
    ]
    return max(chains, key=len)


def where_rungs(node, deref):
    """The `Image.where` nodes on `node`'s receiver spine, outermost first."""
    return [
        current
        for current in _spine(deref(node), deref, _RECEIVER_ARG)
        if (call := _call(current)) is not None and call.get("functionName") == "Image.where"
    ]


def stack_terms(image):
    """`{band position: (soc_final index, change base index, factored index, rungs)}`.

    Reads each `soc_images.select(...)` at ITS OWN SITE (:143, :146 and :153 are three
    separate uses of `year_index`) and, as `rungs`, how many `.where()` calls that
    band's `organic_carbon_change` was built through. The rung count is what shows the
    accumulator is CARRIED: :141-151 adds two `.where()` per iteration to the previous
    iteration's image, so band p is built through 2*(p-1) of them. A loop that rebuilt
    the accumulator from the first block each pass would produce the same node count,
    the same gates and the same values -- and a constant rung count.
    """
    deref, _graph, _root_node = _root(image)
    terms = {}
    for position, node in enumerate(soc_stack(image)):
        call = _call(node)
        if call is None or call.get("functionName") != "Image.subtract":
            continue
        accumulator = deref(call["arguments"]["image2"])
        rungs = where_rungs(accumulator, deref)

        if position == 1:
            # :84 `soc.subtract(organic_carbon_change)` -- the masked grid itself,
            # not a `select`, and the first block's change is not a `where` at all.
            terms[position] = (None, None, None, len(rungs))
            continue

        # rungs[0] is `.where(gt(20), 0)`; rungs[1] is this iteration's own update.
        update = _call(rungs[1])
        divide = _call(deref(update["arguments"]["value"]))
        inner = _call(deref(divide["arguments"]["image1"]))
        factored = deref(inner["arguments"]["image2"])
        while (chain := _call(factored)) is not None and chain["functionName"] == "Image.multiply":
            factored = deref(chain["arguments"]["image1"])

        terms[position] = (
            band_index(call["arguments"]["image1"], deref),
            band_index(inner["arguments"]["image1"], deref),
            band_index(factored, deref),
            len(rungs),
        )
    return terms


def transition_depths(image):
    """`(sorted where-rung counts, the deepest chain's terminal function)`.

    `lc_transition` at each block, read off the receiver of every remap through
    C_CONVERSION_FACTOR. :115 wraps the PREVIOUS block's image in one more `.where()`,
    so the counts must be 0, 1, ... one per block, all bottoming out at the first
    pair's `Image.add`.
    """
    deref, graph, root = _root(image)
    transitions = [
        deref(call["arguments"]["image"])
        for node in _walk(root, deref, graph)
        if (call := _call(node)) is not None
        and call.get("functionName") == "Image.remap"
        and tuple(_scalar_list_arg(deref(call["arguments"]["to"]), deref))
        == tuple(C_CONVERSION_FACTOR)
    ]
    deepest = max(transitions, key=lambda node: len(where_rungs(node, deref)))
    terminal = _spine(deepest, deref, _RECEIVER_ARG)[-1]
    return (
        sorted(len(where_rungs(node, deref)) for node in transitions),
        (_call(terminal) or {}).get("functionName"),
    )


def remap_tables(image):
    """`{(from, to)}` for every `Image.remap` in the graph.

    A set, not a list: MANAGEMENT_FACTOR and INPUT_FACTOR are both 49 ones, so the
    two remaps that carry them are structurally identical and the serializer stores
    one node for both.
    """
    deref, graph, root = _root(image)
    tables = set()
    for node in _walk(root, deref, graph):
        call = _call(node)
        if call is None or call.get("functionName") != "Image.remap":
            continue
        tables.add(
            (
                tuple(_scalar_list_arg(deref(call["arguments"]["from"]), deref)),
                tuple(_scalar_list_arg(deref(call["arguments"]["to"]), deref)),
            )
        )
    return tables


def wheres_by_test(image):
    """`({(comparison, constant): [value node]}, deref)` over every `Image.where`.

    Keyed by the comparison AND its constant, so a `gt` silently becoming a `gte`, or
    a 20 becoming a 25, moves the entry to a key nothing asserts on.
    """
    deref, graph, root = _root(image)
    found = {}
    for node in _walk(root, deref, graph):
        call = _call(node)
        if call is None or call.get("functionName") != "Image.where":
            continue
        key = comparison(deref(call["arguments"]["test"]), deref)
        if key is None:
            continue
        found.setdefault(key, []).append(deref(call["arguments"]["value"]))
    return found, deref


def where_ladder(image):
    """`[(comparison, constant, value constant)]` down the result's `where` spine.

    Outermost first, which is the REVERSE of the source order: `.where(a).where(b)`
    nests as `where(where(x, a), b)`.
    """
    deref, _graph, root = _root(image)
    rungs = []
    for node in _spine(root, deref, _RECEIVER_ARG):
        call = _call(node)
        if call is None or call.get("functionName") != "Image.where":
            continue
        test = deref(call["arguments"]["test"])
        rungs.append(
            (
                comparison(test, deref),
                _image_constant(deref(call["arguments"]["value"]), deref),
            )
        )
    return rungs


def spine_functions(node, deref):
    return [(_call(n) or {}).get("functionName") for n in _spine(node, deref, _RECEIVER_ARG)]


# --- the defect, stated against the tables themselves -------------------------


def test_scale_100_codes_are_exactly_the_ipcc_domain():
    """soil_organic_carbon.py:50 -- the first pair is encoded correctly."""
    codes = sorted(set(TRANSLATION_MATRIX[1]))
    scale_100 = {a * 100 + b for a in codes for b in codes}

    assert scale_100 == set(IPCC_TRANSITION_CODES)
    assert len(scale_100) == 49


def test_scale_10_codes_are_disjoint_from_the_ipcc_domain():
    """soil_organic_carbon.py:114 -- from year two onward the transition codes are
    110..770, which no entry of IPCC_TRANSITION_CODES matches, so `Image.remap` (no
    defaultValue) masks every changed pixel out of the three stock-change remaps."""
    codes = sorted(set(TRANSLATION_MATRIX[1]))
    scale_10 = {a * 10 + b for a in codes for b in codes}

    assert len(scale_10) == 49
    assert scale_10.isdisjoint(set(IPCC_TRANSITION_CODES))


# --- soc_transition_code, the one place the multiplier lives ------------------


def code_parts(scale):
    """`(multiplied constant, scale, added constant)` of `soc_transition_code`'s node.

    The two inputs are `ee.Image(1)` and `ee.Image(2)` so the OPERAND ORDER is
    readable off the graph: `lc1.multiply(s).add(lc0)` is an equally plausible node
    that decodes every transition backwards.
    """
    node = soc_transition_code(ee.Image(1), ee.Image(2), scale)
    deref, _graph, root = _root(node)

    add = _call(root)
    assert add is not None and add["functionName"] == "Image.add"
    multiply = _call(deref(add["arguments"]["image1"]))
    assert multiply is not None and multiply["functionName"] == "Image.multiply"

    return (
        _image_constant(deref(multiply["arguments"]["image1"]), deref),
        _image_constant(deref(multiply["arguments"]["image2"]), deref),
        _image_constant(deref(add["arguments"]["image2"]), deref),
    )


def test_soc_transition_code_multiplies_the_first_image_by_the_scale():
    """soil_organic_carbon.py:50 / :114 -- `lc_time0.multiply(scale).add(lc_time1)`."""
    assert code_parts(100) == (1, 100, 2)
    assert code_parts(10) == (1, 10, 2)


# --- D13 in the built graph ---------------------------------------------------


def test_the_first_pair_is_encoded_at_100_and_every_later_pair_at_10():
    """soil_organic_carbon.py:50 against :114, and :95's `range(start + 1, end)`.

    The pairs are consecutive and cover the whole period, so this also pins the loop
    bounds: an off-by-one at either end changes which years appear as keys."""
    expected = {(SOC_START, SOC_START + 1): 100}
    expected.update({(year, year + 1): 10 for year in LOOP_YEARS})

    assert transition_scales(soc_image()) == expected


def test_the_compatibility_flag_moves_every_later_pair_to_100():
    """`soc_transition_code` is the only place the multiplier is spelled (D13), so
    one flag has to move every loop pair and leave the first pair alone."""
    scales = transition_scales(
        soc_image(compatibility=Compatibility(soc_subsequent_transition_scale=100))
    )

    assert set(scales.values()) == {100}
    assert set(scales) == {(year, year + 1) for year in [SOC_START, *LOOP_YEARS]}


def test_the_default_subsequent_scale_is_the_legacy_ten():
    """The defect ships on by default; the flag exists so the repair is one argument."""
    assert Compatibility().soc_subsequent_transition_scale == 10


def test_the_transition_and_the_change_update_only_where_the_cover_changed():
    """:115 and :141-142. Both updates are gated on `lc_time0.neq(lc_time1)`, and it
    is that gate -- not the scale -- that confines D13's damage to changed pixels:
    unchanged pixels keep the correct four-digit code from the first pair. Flipping
    either `neq` to `eq` inverts which pixels are updated and is invisible to every
    shape assertion above, so both gates and both operands are pinned here."""
    deref, graph, root = _root(soc_image())

    transition_updates, change_updates = [], []
    for node in _walk(root, deref, graph):
        call = _call(node)
        if call is None or call.get("functionName") != "Image.where":
            continue
        value = deref(call["arguments"]["value"])
        value_call = _call(value)
        if value_call is None:
            continue
        if value_call.get("functionName") == "Image.add":
            multiply = _call(deref(value_call["arguments"]["image1"]))
            if multiply is None or multiply.get("functionName") != "Image.multiply":
                continue
            if _image_constant(deref(multiply["arguments"]["image2"]), deref) is None:
                continue
            transition_updates.append((call, multiply, value_call))
        elif value_call.get("functionName") == "Image.divide":
            # `ee.Image(1).divide(coef)` at :126 is also a where-value divide; the
            # stock change is the one whose numerator is the `base - base*c*m*i`
            # subtraction.
            numerator = _call(deref(value_call["arguments"]["image1"]))
            if numerator is not None and numerator.get("functionName") == "Image.subtract":
                change_updates.append(call)

    assert len(transition_updates) == len(LOOP_YEARS)
    assert len(change_updates) == len(LOOP_YEARS)

    for where, multiply, add in transition_updates:
        test = deref(where["arguments"]["test"])
        assert comparison(test, deref) == ("Image.neq", None)
        operands = _call(test)["arguments"]
        # the gate compares the SAME two images the code it guards is built from
        assert id(deref(operands["image1"])) == id(deref(multiply["arguments"]["image1"]))
        assert id(deref(operands["image2"])) == id(deref(add["arguments"]["image2"]))

    for where in change_updates:
        assert comparison(deref(where["arguments"]["test"]), deref) == ("Image.neq", None)


# --- the years that reach the graph -------------------------------------------


def test_the_collection_is_filtered_to_the_soc_period_not_the_land_cover_one():
    """soil_organic_carbon.py:15-17. The stub's land-cover years are 2001/2015 and its
    SOC years 1996/2003, so a builder reading `lc_year_*_esa` lands a different
    window rather than an identical one."""
    deref, graph, root = _root(soc_image())

    assert (SOC_START, SOC_END) in _calendar_windows(root, deref, graph)


def test_every_cci_year_in_the_period_is_filtered_and_nothing_outside_it():
    """:31-47 and :96-106 -- the two blocks between them touch every year from the
    start to the end inclusive, and nothing outside it.

    Not "exactly once": this is a SET of windows, which carries no multiplicity, and
    a post-CSE graph collapses a repeated filter into one node anyway.
    """
    deref, graph, root = _root(soc_image())
    degenerate = {w for w in _calendar_windows(root, deref, graph) if w[0] == w[1]}

    assert degenerate == {(year, year) for year in range(SOC_START, SOC_END + 1)}


def test_each_band_reads_its_own_year_index_at_every_site():
    """:139 `year_index = year - p_soc_t_start`, read at THREE separate sites -- :143
    and :146 inside the change term, and :153 for `soc_final`.

    Asserted per site. A set union over the graph cannot do this: shifting one of the
    three by -1 leaves the union unchanged, because the other two still contribute
    the index it dropped. Band p of `soc_images` is built from band p-1, so all three
    sites must read p-1 for every p.
    """
    terms = stack_terms(soc_image())
    expected = {1: (None, None, None, 0)}
    expected.update(
        {
            position: (position - 1, position - 1, position - 1, 2 * (position - 1))
            for position in range(2, len(LOOP_YEARS) + 2)
        }
    )

    assert terms == expected


def test_no_band_outside_the_stack_is_selected():
    """:161 `select(lc_year_end - p_soc_t_start)` and :162 `select(0)`, plus the loop's
    own indices. A population check, and only that -- it says nothing about which site
    read what, which is why the test above exists."""
    expected = {0, SOC_END - SOC_START}
    expected.update(year - SOC_START for year in LOOP_YEARS)

    assert select_indices(soc_image()) == expected


def test_the_carbon_change_accumulator_is_carried_across_iterations():
    """:141-151. `organic_carbon_change` on the right-hand side is the PREVIOUS
    iteration's image, not a fresh one: each pass wraps it in two more `.where()`
    calls, so the depths must climb 0, 2, 4, ... A loop that rebuilt it from the first
    block every pass emits the same nodes, the same gates and the same values, and is
    invisible to every count in this file."""
    depths = [rungs for *_indices, rungs in stack_terms(soc_image()).values()]

    assert depths == [2 * step for step in range(len(LOOP_YEARS) + 1)]


def test_the_transition_code_is_carried_across_iterations():
    """:115. `lc_transition` is likewise carried -- each pass wraps the previous
    block's image in one more `.where()`, and every chain bottoms out at the first
    pair's `Image.add` (:50). This is what makes the D13 damage cumulative: a pixel
    that changed in year 3 keeps its scale-10 code for every later year."""
    depths, terminal = transition_depths(soc_image())

    assert depths == list(range(BLOCKS))
    assert terminal == "Image.add"


# --- the soc grid --------------------------------------------------------------


def test_only_the_soc_grid_the_cci_collection_and_the_climate_zones_are_loaded():
    assert _loaded_asset_ids(soc_image()) == {
        ASSETS["soc"],
        ASSETS["land_cover_ic"],
        ASSETS["ipcc_climate_zones"],
    }


def test_the_soc_grid_is_clipped_to_the_bounds_and_masked_where_it_is_int16_min():
    """:9-10. `neq`, not `eq`: the mask keeps everything that is NOT the nodata
    sentinel, and the flipped comparison would mask the entire grid instead."""
    deref, graph, root = _root(soc_image())

    masks = [
        call
        for node in _walk(root, deref, graph)
        if (call := _call(node)) is not None and call.get("functionName") == "Image.updateMask"
    ]
    # exactly 1: :10 is the only updateMask in the whole transcription.
    assert len(masks) == 1

    assert comparison(deref(masks[0]["arguments"]["mask"]), deref) == ("Image.neq", INT16_MIN)
    assert spine_functions(masks[0]["arguments"]["image"], deref) == [
        "Image.clip",
        "Image.load",
    ]

    clip = _call(deref(masks[0]["arguments"]["image"]))
    assert _call(deref(clip["arguments"]["geometry"]))["functionName"] == "Geometry.bounds"


# --- the climate coefficient ---------------------------------------------------


def test_per_pixel_climate_remaps_the_ipcc_zones_clipped_to_the_bounds():
    """:20-25. The two rows of CLIMATE_CONVERSION_MATRIX are both numeric and the same
    length, so a swapped pair of remap arguments builds an equally plausible graph."""
    coefficient = climate_coefficient(make_resolved(climate=PerPixelClimate()), aoi_context())

    assert isinstance(coefficient, ee.Image)
    assert _loaded_asset_ids(coefficient) == {ASSETS["ipcc_climate_zones"]}
    assert remap_tables(coefficient) == {
        (tuple(CLIMATE_CONVERSION_MATRIX[0]), tuple(CLIMATE_CONVERSION_MATRIX[1]))
    }

    deref, _graph, root = _root(coefficient)
    assert spine_functions(root, deref) == ["Image.remap", "Image.clip", "Image.load"]
    clip = _call(deref(_call(root)["arguments"]["image"]))
    assert _call(deref(clip["arguments"]["geometry"]))["functionName"] == "Geometry.bounds"


def test_fixed_climate_is_the_bare_coefficient():
    """:27 -- a plain float, which `Image.where` accepts as its `value`."""
    coefficient = climate_coefficient(
        make_resolved(climate=FixedClimate(coefficient=0.8)), aoi_context()
    )

    assert coefficient == pytest.approx(0.8)
    assert not isinstance(coefficient, ee.Image)


def test_fixed_climate_keeps_the_zone_asset_out_of_the_graph():
    """The dispatch is observable end to end, not only through `climate_coefficient`."""
    assert _loaded_asset_ids(soc_image(climate=FixedClimate(coefficient=0.8))) == {
        ASSETS["soc"],
        ASSETS["land_cover_ic"],
    }


def test_a_zero_coefficient_takes_the_fixed_branch_where_the_legacy_took_per_pixel():
    """EXPECTED_DIVERGENCES 2 -- soil_organic_carbon.py:19 tests `if not
    model.conversion_coef`, i.e. TRUTHINESS, so 0.0 fell to the per-pixel IPCC
    remap. The tagged union sends it to the fixed branch, which is a different
    graph and not an error. None of the five UI coefficients is 0.0, but
    FixedClimate is unconstrained and validate() does not bound it, so this pins
    which way the port goes rather than leaving it to be discovered."""
    coefficient = climate_coefficient(
        make_resolved(climate=FixedClimate(coefficient=0.0)), aoi_context()
    )

    assert coefficient == 0.0
    assert not isinstance(coefficient, ee.Image)
    assert _loaded_asset_ids(soc_image(climate=FixedClimate(coefficient=0.0))) == {
        ASSETS["soc"],
        ASSETS["land_cover_ic"],
    }


def test_an_unsupported_climate_regime_raises_spec_error():
    """EXPECTED_DIVERGENCES 1 -- no legacy counterpart; the legacy if/else is total."""
    with pytest.raises(SpecError, match="unsupported climate regime"):
        climate_coefficient(make_resolved(climate=object()), aoi_context())


def test_the_coefficient_is_inverted_on_the_negative_sentinel_only():
    """:60-65 and :122-127. The 333 branch takes the coefficient itself and the -333
    branch its RECIPROCAL; exchanging the two, or writing `coef` on both, is silent."""
    wheres, deref = wheres_by_test(soc_image())

    positive = wheres[("Image.eq", 333)]
    negative = wheres[("Image.eq", -333)]
    assert len(positive) == BLOCKS
    assert len(negative) == BLOCKS

    coefficients = {id(node) for node in positive}
    # one shared node: every block recodes with the SAME climate coefficient image.
    assert len(coefficients) == 1
    assert _call(positive[0])["functionName"] == "Image.remap"

    for value in negative:
        divide = _call(value)
        assert divide["functionName"] == "Image.divide"
        assert _image_constant(deref(divide["arguments"]["image1"]), deref) == 1
        assert id(deref(divide["arguments"]["image2"])) in coefficients


# --- the stock-change tables ----------------------------------------------------


def test_each_stock_change_table_goes_into_its_own_remap():
    """:57-75 and :119-137, plus the land-cover translation at :36 / :46.

    MANAGEMENT_FACTOR and INPUT_FACTOR are both 49 ones, so their two remaps are
    structurally identical and the serializer keeps one node -- which is why this is
    a set of four and not of five."""
    assert MANAGEMENT_FACTOR == INPUT_FACTOR

    assert remap_tables(soc_image()) == {
        (tuple(TRANSLATION_MATRIX[0]), tuple(TRANSLATION_MATRIX[1])),
        (tuple(CLIMATE_CONVERSION_MATRIX[0]), tuple(CLIMATE_CONVERSION_MATRIX[1])),
        (tuple(IPCC_TRANSITION_CODES), tuple(C_CONVERSION_FACTOR)),
        (tuple(IPCC_TRANSITION_CODES), tuple(MANAGEMENT_FACTOR)),
    }


def carbon_change_terms(image):
    """`[(base is also the factored image, factor count)]` per `.divide(20)` node.

    The stock change at :77-81 and :144-150 is ``base - base*c*m*i`` over twenty
    years. Walking the multiply chain back to its innermost receiver is what shows
    the SAME image on both sides of the subtraction: `soc - other*c*m*i` would be an
    equally well-shaped graph.
    """
    deref, graph, root = _root(image)
    terms = []
    for node in _walk(root, deref, graph):
        call = _call(node)
        if call is None or call.get("functionName") != "Image.divide":
            continue
        if _image_constant(deref(call["arguments"]["image2"]), deref) != 20:
            continue
        subtract = _call(deref(call["arguments"]["image1"]))
        assert subtract["functionName"] == "Image.subtract"

        base = deref(subtract["arguments"]["image1"])
        factored = deref(subtract["arguments"]["image2"])
        factors = 0
        while (chain := _call(factored)) is not None and chain["functionName"] == "Image.multiply":
            factors += 1
            factored = deref(chain["arguments"]["image1"])
        terms.append((id(base) == id(factored), factors))
    return terms


def test_the_stock_change_is_the_image_less_its_factored_self_over_twenty_years():
    """:77-81 and :144-150 -- three factors (climate, management, organic input), the
    same image on both sides of the subtraction, divided by the IPCC twenty-year
    transition period. The divisor is not the 20 of :151: that one is a year COUNT
    on `lc_transition_time`, which is why they are pinned separately."""
    assert carbon_change_terms(soc_image()) == [(True, 3)] * BLOCKS


# --- the years-since-transition counter -----------------------------------------


def counter_spine(image):
    """`[(comparison, value description)]` down the deepest counter's `where` spine.

    The counter is `lc_transition_time`, reachable as the receiver of the
    `.gt(20)` nodes at :151. The deepest one carries every iteration's update, so its
    spine is the whole :108-110 history, outermost first.
    """
    deref, graph, root = _root(image)
    counters = [
        deref(call["arguments"]["image1"])
        for node in _walk(root, deref, graph)
        if (call := _call(node)) is not None and comparison(node, deref) == ("Image.gt", 20)
    ]
    spines = [_spine(counter, deref, _RECEIVER_ARG) for counter in counters]
    deepest = max(spines, key=len)

    rungs = []
    for node in deepest:
        call = _call(node)
        if call is None or call.get("functionName") != "Image.where":
            rungs.append(((_call(node) or {}).get("functionName"), _image_constant(node, deref)))
            continue
        value = deref(call["arguments"]["value"])
        value_call = _call(value)
        rungs.append(
            (
                comparison(deref(call["arguments"]["test"]), deref),
                (
                    value_call.get("functionName"),
                    _image_constant(deref(value_call["arguments"]["image2"]), deref)
                    if value_call.get("functionName") == "Image.add"
                    else _image_constant(value, deref),
                ),
            )
        )
    return rungs


def test_the_counter_increments_where_the_pair_is_equal_then_resets_where_it_is_not():
    """:53 and :108-110. The order of the two `.where()` calls is load-bearing -- the
    RESET is the outer one, so a year that changed is recorded as year 1 and not as
    the previous count plus one. The seed is `ee.Image(2)`, not 1 or 0."""
    increment = (("Image.eq", None), ("Image.add", 1))
    reset = (("Image.neq", None), ("Image.constant", 1))

    # outermost first: the deepest counter is LOOP_YEARS passes of (reset, increment)
    # over :53's own `where(neq, 1)` on a seed of 2.
    assert counter_spine(soc_image()) == [
        *[rung for _year in LOOP_YEARS for rung in (reset, increment)],
        reset,
        ("Image.constant", 2),
    ]


def test_the_accumulated_change_is_zeroed_once_the_counter_passes_twenty():
    """:151 `.where(lc_transition_time.gt(20), 0)`, applied AFTER the update at
    :141-150. `gt`, not `gte`: a counter of exactly 20 still accumulates."""
    wheres, deref = wheres_by_test(soc_image())

    zeroed = wheres[("Image.gt", 20)]
    assert len(zeroed) == len(LOOP_YEARS)
    assert {_image_constant(node, deref) for node in zeroed} == {0}

    deref, graph, root = _root(soc_image())
    outer = [
        call
        for node in _walk(root, deref, graph)
        if (call := _call(node)) is not None
        and call.get("functionName") == "Image.where"
        and comparison(deref(call["arguments"]["test"]), deref) == ("Image.gt", 20)
    ]
    for call in outer:
        inner = _call(deref(call["arguments"]["input"]))
        assert inner["functionName"] == "Image.where"
        assert _call(deref(inner["arguments"]["value"]))["functionName"] == "Image.divide"


# --- percent change and the byte convention -------------------------------------


def test_the_percent_change_is_the_last_band_against_the_first():
    """:160-165 -- `(last - first) / first * 100`. Both the operand order and the
    divisor are pinned: `(first - last)` and `/ last` are equally plausible nodes."""
    deref, _graph, root = _root(soc_image())

    ladder = _spine(root, deref, _RECEIVER_ARG)
    seed = ladder[-1]
    assert _image_constant(seed, deref) == 0

    percent = deref(_call(ladder[-2])["arguments"]["test"])
    # the innermost rung's test is `soc_percent_change.gt(10)`; walk into it.
    multiply = _call(deref(_call(percent)["arguments"]["image1"]))
    assert multiply["functionName"] == "Image.multiply"
    assert _image_constant(deref(multiply["arguments"]["image2"]), deref) == 100

    divide = _call(deref(multiply["arguments"]["image1"]))
    assert divide["functionName"] == "Image.divide"

    subtract = _call(deref(divide["arguments"]["image1"]))
    assert subtract["functionName"] == "Image.subtract"

    def band(node):
        return _scalar_list_arg(deref(_call(deref(node))["arguments"]["bandSelectors"]), deref)

    assert band(subtract["arguments"]["image1"]) == [SOC_END - SOC_START]
    assert band(subtract["arguments"]["image2"]) == [0]
    assert band(divide["arguments"]["image2"]) == [0]


def test_the_output_is_a_single_uint8_soc_band_over_a_seed_of_zero():
    """:169-176."""
    deref, _graph, root = _root(soc_image())

    assert spine_functions(root, deref) == [
        "Image.uint8",
        "Image.rename",
        "Image.where",
        "Image.where",
        "Image.where",
        "Image.constant",
    ]
    rename = _call(_spine(root, deref, _RECEIVER_ARG)[1])
    assert _scalar_list_arg(deref(rename["arguments"]["names"]), deref) == ["soc"]


def test_the_degradation_ladder_leaves_both_ten_boundaries_open():
    """:169-176. At a percent change of exactly 10 or exactly -10 no rung fires and
    the pixel keeps the seed 0, which :167's comment calls nodata rather than a
    class. Tidying `lt` into `lte` -- or flipping any of the four comparisons --
    closes a hole the published results have, so every operator is pinned here."""
    assert where_ladder(soc_image()) == [
        (("Image.lt", -10), 1),
        (None, 2),  # `lt(10).And(gt(-10))` is an Image.and, not a bare comparison
        (("Image.gt", 10), 3),
    ]


def test_the_stable_rung_is_the_conjunction_of_two_open_bounds():
    """:172 -- `ee.Image.And` is an instance method and keeps both operands (unlike
    `ee.Filter.And`, the staticmethod Task 11 found discarding its receiver)."""
    deref, _graph, root = _root(soc_image())

    stable = deref(_call(_spine(root, deref, _RECEIVER_ARG)[3])["arguments"]["test"])
    conjunction = _call(stable)
    assert conjunction["functionName"] == "Image.and"

    assert comparison(deref(conjunction["arguments"]["image1"]), deref) == ("Image.lt", 10)
    assert comparison(deref(conjunction["arguments"]["image2"]), deref) == ("Image.gt", -10)


# --- the real resolve() ---------------------------------------------------------


def resolved_soc(start, end):
    periods = replace(DEFAULT_PERIODS, soc=PeriodOverride(start, end))
    return resolve(default_spec(periods=periods))


def test_the_soc_start_year_reaches_the_graph_unclamped():
    """soil_organic_carbon.py:16 passes `p_soc_t_start` raw while :12-14 clamps only
    the end. Both halves of that asymmetry are in this one window: the period
    1980-1985 sits entirely before the CCI collection, so the END is lifted to the
    first CCI year while the START stays twelve years below it."""
    r = resolved_soc(1980, 1985)
    assert (r.soc_year_start, r.soc_year_end_esa) == (1980, LAND_COVER_FIRST_YEAR)

    deref, graph, root = _root(build_soil_organic_carbon(r, aoi_context()))
    windows = _calendar_windows(root, deref, graph)

    assert (1980, LAND_COVER_FIRST_YEAR) in windows
    assert (1980, 1980) in windows


def test_the_soc_end_year_is_clamped_to_the_cci_range():
    """soil_organic_carbon.py:12-14, resolve.py:245. The asymmetry with the start year
    is the point: one endpoint is clamped and the other is not."""
    r = resolved_soc(2018, 2050)
    assert r.soc_year_end_esa == LAND_COVER_MAX_YEAR

    deref, graph, root = _root(build_soil_organic_carbon(r, aoi_context()))
    windows = _calendar_windows(root, deref, graph)

    assert (2018, LAND_COVER_MAX_YEAR) in windows
    assert max(end for _start, end in windows) == LAND_COVER_MAX_YEAR
