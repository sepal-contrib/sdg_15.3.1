"""Graph-shape tests for sdg1531.engine.productivity (legacy productivity.py)."""

from __future__ import annotations

import json

import ee
import pytest

from sdg1531.catalog import z_coefficient
from sdg1531.engine.productivity import (
    _LCEU_BUILDERS,
    _TRAJECTORY_BUILDERS,
    build_lc_ecological_units,
    build_performance,
    build_productivity,
    build_state,
    build_trajectory,
)
from sdg1531.enums import Lceu, Trajectory
from sdg1531.errors import SpecError
from sdg1531.spec import Period
from sdg1531.truth_table import PRODUCTIVITY_GPGV1, PRODUCTIVITY_GPGV2
from tests.engine.conftest import make_resolved


def encoded(obj) -> str:
    """The serialized graph as one string, for substring assertions."""
    return json.dumps(ee.serializer.encode(obj), sort_keys=True)


def count_calls(obj, function_name: str) -> int:
    """Count DISTINCT nodes invoking `function_name`.

    The ee serializer collapses structurally identical subtrees into a single
    scope entry, so this counts distinct nodes, not textual occurrences.
    """
    graph = ee.serializer.encode(obj)
    total = 0
    stack = [graph]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            call = node.get("functionInvocationValue")
            if isinstance(call, dict) and call.get("functionName") == function_name:
                total += 1
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return total


# --- reference-resolving graph walks ----------------------------------------
#
# Deliberately duplicated in spirit from test_integration.py rather than hoisted
# into conftest.py: that file is Task 10's and is shared by Tasks 11-17, and the
# two files need different slices of the walk. What both need is the same
# awareness -- `ee.serializer.encode()` hoists a repeated value into the
# `values` registry and points every use of it at that entry via
# `{"valueReference": K}`, so anything that reads an ARGUMENT's value (rather
# than merely noting a substring) has to resolve the indirection first.


def _deref_for(obj):
    """Return `(deref, graph)` for `obj`'s encoded graph."""
    graph = ee.serializer.encode(obj)
    values = graph.get("values", {})

    def deref(node):
        while isinstance(node, dict) and set(node) == {"valueReference"}:
            node = values[node["valueReference"]]
        return node

    return deref, graph


def _call(node):
    """The `functionInvocationValue` dict of `node`, or None."""
    if isinstance(node, dict):
        call = node.get("functionInvocationValue")
        if isinstance(call, dict):
            return call
    return None


def _walk(node, deref, graph):
    """Yield every resolved node reachable from `node`.

    A `.map()`/`.reduce()` callback body is a bare string key into `values`
    rather than a `{"valueReference": ...}` wrapper, so it is followed
    explicitly -- the second indirection test_integration.py documents.
    """
    values = graph.get("values", {})
    stack = [node]
    seen: set[int] = set()
    while stack:
        current = deref(stack.pop())
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        yield current
        if isinstance(current, dict):
            body = current.get("functionDefinitionValue")
            if isinstance(body, dict) and body.get("body") in values:
                stack.append(values[body["body"]])
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


# The argument each node carries its receiver in: `Image.uint8` spells it
# `value`, the other two `input` (verified against the encoder).
_RECEIVER_ARG = {"Image.where": "input", "Image.rename": "input", "Image.uint8": "value"}


def _image_constant(node, deref):
    """The scalar behind an `ee.Image(k)` argument node, or None."""
    call = _call(node)
    if call is not None and call.get("functionName") == "Image.constant":
        inner = deref(call.get("arguments", {}).get("value", {}))
        if isinstance(inner, dict):
            return inner.get("constantValue")
    return None


def _where_chain(obj):
    """`[(test function name, assigned value), ...]` for the final where chain,
    innermost (first `.where()`) first.

    The order comes from the graph's NESTING -- each step is found by following
    the previous one's receiver argument -- not from a count, so CSE cannot
    collapse it and swapping two `.where()` lines reorders the returned list.
    Only the spine from the result is walked; `.where()` calls sitting in other
    branches (an operand's own chain) are not part of it.
    """
    deref, graph = _deref_for(obj)
    node = deref({"valueReference": graph["result"]})
    steps = []
    while True:
        call = _call(node)
        if call is None:
            break
        name = call.get("functionName")
        if name not in _RECEIVER_ARG:
            break
        args = call.get("arguments", {})
        if name == "Image.where":
            test = _call(deref(args["test"]))
            steps.append(
                (
                    test.get("functionName") if test is not None else None,
                    _image_constant(deref(args["value"]), deref),
                )
            )
        node = deref(args[_RECEIVER_ARG[name]])
    return list(reversed(steps))


def _windows_in(node, deref, graph):
    """`{(field, minValue, maxValue)}` for the `Filter.rangeContains` nodes
    under `node`."""
    windows = set()
    for current in _walk(node, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "Filter.rangeContains":
            continue
        args = call.get("arguments", {})
        windows.add(
            tuple(
                deref(args[key]).get("constantValue") for key in ("field", "minValue", "maxValue")
            )
        )
    return windows


def _selected_bands(obj):
    """Every band name passed to `.select(...)` anywhere in the graph.

    `bandSelectors` is `{"constantValue": [...]}` when inlined and
    `{"arrayValue": {"values": [...]}}` when the list -- or one of its elements
    -- is itself hoisted into `values`, so both are resolved; this is the same
    handling test_integration.py's `_renamed_bands` needs.
    """
    deref, graph = _deref_for(obj)
    names = set()
    for current in _walk({"valueReference": graph["result"]}, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "Image.select":
            continue
        arg = deref(call.get("arguments", {}).get("bandSelectors", {}))
        if not isinstance(arg, dict):
            continue
        if isinstance(arg.get("constantValue"), list):
            items = arg["constantValue"]
        else:
            items = arg.get("arrayValue", {}).get("values", [])
        for item in items:
            value = deref(item)
            if isinstance(value, dict):
                value = value.get("constantValue")
            if isinstance(value, str):
                names.add(value)
    return names


def _range_windows(obj):
    """Every `Filter.rangeContains` window in the graph."""
    deref, graph = _deref_for(obj)
    return _windows_in({"valueReference": graph["result"]}, deref, graph)


def _stddev_windows(obj):
    """The `Filter.rangeContains` windows feeding a `Reducer.stdDev` reduction.

    `_range_windows` alone cannot tell the recent window from the baseline one:
    exchanging the two filters leaves the SET of windows identical. Only the
    baseline period is reduced with stdDev (productivity.py:217-222), so
    reading the window under that reduction is what pins which is which.
    """
    deref, graph = _deref_for(obj)
    for current in _walk({"valueReference": graph["result"]}, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "ImageCollection.reduce":
            continue
        reducer = _call(deref(call.get("arguments", {})["reducer"]))
        if reducer is None or reducer.get("functionName") != "Reducer.stdDev":
            continue
        return _windows_in(call["arguments"]["collection"], deref, graph)
    return set()


def fake_vi_collection() -> ee.ImageCollection:
    """A stand-in for build_vi_collection's output: band `vi`, property `year`."""
    return ee.ImageCollection(
        [ee.Image(0.1 * (year - 2000)).rename("vi").set("year", year) for year in range(2001, 2016)]
    )


def fake_climate_collection() -> ee.ImageCollection:
    """A stand-in for build_climate_collection's output: band `clim`."""
    return ee.ImageCollection(
        [ee.Image(float(year)).rename("clim").set("year", year) for year in range(2001, 2016)]
    )


def test_lceu_builders_cover_every_lceu_member():
    # productivity.py:92-116 leaves the local unbound for an unknown lceu.
    assert set(_LCEU_BUILDERS) == set(Lceu)


@pytest.mark.parametrize(
    "lceu, asset",
    [
        (Lceu.GAES, "users/amitghosh/sdg_module/fao/GAES_L4"),
        (Lceu.AEZ, "users/amitghosh/sdg_module/fao/aez_v9v2_CRUTS32_Hist_8110_100_avg"),
        (Lceu.HRU, "users/amitghosh/sdg_module/hru_250"),
        (Lceu.WTE, "users/amitghosh/sdg_module/wte_2020"),
    ],
)
def test_static_ecological_units_load_their_asset(lceu, asset):
    r = make_resolved(lceu=lceu)

    assert asset in encoded(build_lc_ecological_units(r))


def test_calculated_ecological_unit_combines_soil_and_land_cover():
    r = make_resolved(lceu=Lceu.CALCULATE, lc_year_start_esa=2001)

    img = build_lc_ecological_units(r)
    graph = encoded(img)

    # productivity.py:99-114: soil taxonomy band b0 * 100 + IPCC-reclassed LC.
    assert "OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02" in graph
    assert "users/amitghosh/sdg_module/esa/cci_landcover" in graph
    assert '"b0"' in graph
    assert count_calls(img, "Image.remap") == 1
    assert count_calls(img, "Image.multiply") == 1
    assert count_calls(img, "Image.add") == 1


def test_trajectory_builders_cover_every_trajectory_member():
    # productivity.py:30-51 leaves z_score unbound for an unhandled trajectory.
    assert set(_TRAJECTORY_BUILDERS) == set(Trajectory)


def test_s_res_trend_raises_a_spec_error_not_a_name_error():
    # productivity.py:42-43 raises a bare NameError from inside the chain; the
    # method is marked disabled at parameter/ui.py:35 and validate() rejects it.
    r = make_resolved(trajectory=Trajectory.S_RES_TREND)

    with pytest.raises(SpecError):
        build_trajectory(r, fake_vi_collection(), fake_climate_collection())


def test_trajectory_emits_both_bands_and_seven_where_nodes():
    r = make_resolved(trajectory=Trajectory.NDVI_TREND, trend=Period(2001, 2015))

    img = build_trajectory(r, fake_vi_collection(), fake_climate_collection())
    graph = encoded(img)

    assert '"trajectory_5_levels"' in graph
    assert '"trajectory"' in graph
    # The 5-level chain has 5 wheres and the 3-level chain 3, but their first
    # node -- ee.Image(0).where(z.lt(-1.96), 1) -- is shared, and the serializer
    # collapses identical subtrees. 5 + 3 - 1 = 7.
    assert count_calls(img, "Image.where") == 7
    assert count_calls(img, "Image.uint8") == 2
    assert count_calls(img, "Image.addBands") == 1


def test_vi_trend_multiplies_the_tau_by_the_z_coefficient():
    r = make_resolved(trajectory=Trajectory.NDVI_TREND, trend=Period(2001, 2015))

    graph = encoded(build_trajectory(r, fake_vi_collection(), fake_climate_collection()))

    # productivity.py:435-442: n = end - start + 1 = 15
    assert str(z_coefficient(15)) in graph
    assert '"vi_tau"' in graph


def test_restrend_fits_one_unsegmented_linear_model():
    # Preserved, not fixed (spec 3): productivity.py:477-480 reduces the whole
    # trend period with a single linearFit, with no breakpoint.
    r = make_resolved(trajectory=Trajectory.P_RES_TREND, trend=Period(2001, 2015))

    img = build_trajectory(r, fake_vi_collection(), fake_climate_collection())
    graph = encoded(img)

    assert count_calls(img, "Reducer.linearFit") == 1
    assert '"vi_res_tau"' in graph
    assert '"offset"' in graph
    assert '"scale"' in graph


def test_rain_use_efficiency_divides_climate_by_one_thousand():
    r = make_resolved(trajectory=Trajectory.UE_TREND, trend=Period(2001, 2015))

    graph = encoded(build_trajectory(r, fake_vi_collection(), fake_climate_collection()))

    # productivity.py:612: clim / 1000, then vi / clim, band "ue".
    assert '"ue_tau"' in graph
    # Brief defect 1 (controller notes): a bare `"1000" in graph` is satisfied
    # by any longer number containing it -- a scale, a year, a projection
    # parameter. The serializer's structured constant form pins the divisor.
    assert '"constantValue": 1000}' in graph


def test_performance_reduces_with_best_effort_at_the_analysis_scale(ctx):
    # Preserved, not fixed (spec 3): productivity.py:141-145 passes
    # bestEffort=True, which silently coarsens the scale on large AOIs.
    r = make_resolved(lceu=Lceu.GAES, performance=Period(2001, 2015), analysis_scale=250)

    img = build_performance(r, ctx, fake_vi_collection())
    graph = encoded(img)

    assert '"bestEffort": {"constantValue": true}' in graph
    # Closing brace included on both: `'"scale": {"constantValue": 250'` alone
    # also matches 2500, and the brief's `'"maxPixels": {"constantValue": 1'`
    # matches any maxPixels beginning with a 1 -- same bare-substring defect
    # class the controller flagged at defect 1.
    assert '"scale": {"constantValue": 250}' in graph
    assert '"maxPixels": {"constantValue": 1000000000000000.0}' in graph
    assert count_calls(img, "Image.reduceRegion") == 1
    assert count_calls(img, "Reducer.percentile") == 1


def test_performance_stays_server_side_through_remap(ctx):
    # The reduceRegion result is consumed as ee.List(...).get("groups") and fed
    # back into remap; nothing is fetched. productivity.py:150-155.
    r = make_resolved(lceu=Lceu.GAES, performance=Period(2001, 2015))

    img = build_performance(r, ctx, fake_vi_collection())
    graph = encoded(img)

    assert '"groups"' in graph
    assert '"code"' in graph
    assert '"p90"' in graph
    assert count_calls(img, "Image.remap") == 1


def test_performance_names_and_types_its_band(ctx):
    r = make_resolved(lceu=Lceu.GAES, performance=Period(2001, 2015))

    img = build_performance(r, ctx, fake_vi_collection())
    graph = encoded(img)

    assert '"performance"' in graph
    assert count_calls(img, "Image.uint8") == 1
    # ee.Image(-1).where(lceu, lceu); the 0 -> 0.001 guard; and the two
    # observed-ratio classes. productivity.py:133, :157, :166-172.
    assert count_calls(img, "Image.where") == 4
    # Brief defect 2 (controller notes): `"0.001" in graph` is a bare substring.
    assert '"constantValue": 0.001}' in graph


def test_performance_classifies_a_ratio_of_exactly_one_half_as_degraded(ctx):
    # productivity.py:166-172's two conditions OVERLAP at exactly 0.5:
    # `.gte(0.5)` assigns 2 and the LATER `.lte(0.5)` overwrites it with 1, so
    # a pixel sitting exactly on the threshold is degraded, not stable. That
    # ordering is the most behaviour-defining line in build_performance and
    # nothing else here holds it -- swapping the two `.where()` lines leaves
    # the where COUNT, every band name and every constant in the graph
    # unchanged. Walking the chain's NESTING is what makes the swap visible.
    r = make_resolved(lceu=Lceu.GAES, performance=Period(2001, 2015))

    img = build_performance(r, ctx, fake_vi_collection())

    assert _where_chain(img) == [("Image.gte", 2), ("Image.lte", 1)]


def test_state_compares_the_last_three_years_to_the_baseline():
    r = make_resolved(state=Period(2001, 2015))

    img = build_state(r, fake_vi_collection())
    graph = encoded(img)

    # productivity.py:195-200: recent = [end-2, end], baseline = [start, end-3].
    # Brief defect 4 (controller notes): the original
    # `'"rangeContains"' in graph or "rangeContains" in graph` had a second
    # disjunct that subsumed the first, so the quoted form was never required.
    # Reading the two filters' actual bounds is the structured replacement.
    assert _range_windows(img) == {("year", 2013, 2015), ("year", 2001, 2012)}
    # ... and which window is which: only the baseline is reduced with stdDev,
    # so exchanging the two filters -- which the set above cannot see -- flips
    # the sign of the z-score and fails here.
    assert _stddev_windows(img) == {("year", 2001, 2012)}
    assert '"constantValue": 2013' in graph
    assert '"constantValue": 2012' in graph
    assert '"constantValue": 2015' in graph
    assert '"constantValue": 2001' in graph


def test_state_emits_both_bands_and_seven_where_nodes():
    r = make_resolved(state=Period(2001, 2015))

    img = build_state(r, fake_vi_collection())
    graph = encoded(img)

    assert '"state_5_levels"' in graph
    assert '"state"' in graph
    # Same shared-first-node arithmetic as the trajectory chains: 5 + 3 - 1.
    assert count_calls(img, "Image.where") == 7
    assert count_calls(img, "Reducer.stdDev") == 1
    assert count_calls(img, "Image.uint8") == 2


def fake_trajectory() -> ee.Image:
    """Stand-in for build_trajectory's output: the two trajectory bands.

    The real builder casts each band with ``.uint8()``; the stand-ins do not,
    so that every ``Image.uint8`` node in the collapse graph can only come from
    build_productivity's own terminal cast.
    """
    five_levels = ee.Image(3).rename("trajectory_5_levels")
    return five_levels.addBands(ee.Image(2).rename("trajectory"))


def fake_state() -> ee.Image:
    """Stand-in for build_state's output; uncast, for the same reason."""
    five_levels = ee.Image(3).rename("state_5_levels")
    return five_levels.addBands(ee.Image(2).rename("state"))


def fake_performance() -> ee.Image:
    """Stand-in for build_performance's output; uncast, for the same reason."""
    return ee.Image(2).rename("performance")


def _collapse(table) -> ee.Image:
    """build_productivity over the three stand-ins, for `table`."""
    return build_productivity(
        make_resolved(productivity_table=table),
        trajectory=fake_trajectory(),
        state=fake_state(),
        performance=fake_performance(),
    )


def test_productivity_collapse_emits_one_where_per_rule():
    img = _collapse(PRODUCTIVITY_GPGV2)
    graph = encoded(img)

    # productivity.py:252-334 -- 18 rules, all distinct conditions.
    assert len(PRODUCTIVITY_GPGV2.rules) == 18
    assert count_calls(img, "Image.where") == 18
    assert '"productivity"' in graph
    assert count_calls(img, "Image.uint8") == 1


def test_productivity_collapse_assigns_each_rule_s_value_in_table_order():
    # The count above is a post-CSE node count and says nothing about ORDER or
    # about WHICH class each rule assigns; the chain's nesting says both. This
    # is what ties the emitted graph to the table data (spec D9: same nodes, in
    # the same order), and it fails if any cell of the table is edited, if two
    # rules are transposed, or if a rule is dropped.
    img = _collapse(PRODUCTIVITY_GPGV2)

    assert [value for _test, value in _where_chain(img)] == [
        rule.value for rule in PRODUCTIVITY_GPGV2.rules
    ]


def test_productivity_selects_the_three_input_bands_by_name():
    img = _collapse(PRODUCTIVITY_GPGV2)
    graph = encoded(img)

    # productivity.py:253-255 selects one band from each input image once and
    # reuses it, so the collapse carries exactly three Image.select nodes.
    # Selecting does not prune the parent graph -- the 5-level rename nodes
    # stay reachable through the selected image -- so this counts the selects
    # rather than asserting the 5-level names are absent.
    assert count_calls(img, "Image.select") == 3
    # WHICH three bands, not just how many selects: the three checks below are
    # satisfied by the stand-ins' own `.rename()` calls whatever
    # build_productivity selects (`.select("trajectory_5_levels")` would leave
    # all three standing), so on their own they cannot fail. The stand-ins
    # contain no `.select` of their own, so these names come only from here.
    assert _selected_bands(img) == {"trajectory", "state", "performance"}
    assert '"trajectory"' in graph
    assert '"state"' in graph
    assert '"performance"' in graph


def test_the_two_lookup_tables_build_different_graphs():
    # productivity.py:252-334 vs :337-419 differ in exactly two cells.
    v2 = _collapse(PRODUCTIVITY_GPGV2)
    v1 = _collapse(PRODUCTIVITY_GPGV1)

    assert encoded(v1) != encoded(v2)
    # ... at rules 4 and 9 (1-based), and nowhere else: byte inequality alone
    # would also pass if the two graphs differed for some unrelated reason.
    v1_values = [value for _test, value in _where_chain(v1)]
    v2_values = [value for _test, value in _where_chain(v2)]
    assert [i for i, (a, b) in enumerate(zip(v1_values, v2_values, strict=True)) if a != b] == [
        3,
        8,
    ]
