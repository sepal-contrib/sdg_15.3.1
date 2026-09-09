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
    build_trajectory,
)
from sdg1531.enums import Lceu, Trajectory
from sdg1531.errors import SpecError
from sdg1531.spec import Period
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


def _calls(obj):
    """Yield `(deref, call)` for every `functionInvocationValue` in the graph.

    Walking the raw encoded graph visits each `values` entry exactly once;
    `deref` is bound to that same graph so a hoisted argument can be read back.
    """
    deref, graph = _deref_for(obj)
    stack = [graph]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            call = node.get("functionInvocationValue")
            if isinstance(call, dict):
                yield deref, call
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


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


def _range_windows(obj):
    """`{(field, minValue, maxValue)}` for every `Filter.rangeContains` node."""
    windows = set()
    for deref, call in _calls(obj):
        if call.get("functionName") != "Filter.rangeContains":
            continue
        args = call.get("arguments", {})
        windows.add(
            tuple(
                deref(args[key]).get("constantValue") for key in ("field", "minValue", "maxValue")
            )
        )
    return windows


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
