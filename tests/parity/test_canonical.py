"""The canonicaliser is the thing that decides whether two graphs match.

It is therefore exactly the thing that must not be taken on trust. Every helper on
this plan that quietly agreed with itself did so by comparing a projection of the
graph -- a set of function names, a multiset of argument names, a node count --
that could not see the difference it was asked about. So these tests come in
pairs: for each degree of freedom the canonical form is meant to REMOVE there is a
test that a change in it is invisible, and for each thing it is meant to KEEP
there is a test that a change in it is visible.

The graphs are small ones built here rather than corpus goldens, except where a
real graph's size and `.map()` callbacks are the point. `test_parity.py` runs the
same code over all 19 graph-producing scenarios.
"""

from __future__ import annotations

import json
from pathlib import Path

import ee
import pytest

from tests.parity.canonical import (
    INDICATOR_BAND,
    canonical_graph,
    function_name_counts,
    render,
    strip_indicator_band_rename,
)

GOLDEN = Path(__file__).resolve().parents[1] / "golden"


def encode(image: ee.Image) -> dict:
    return ee.serializer.encode(image)


def a_real_graph() -> dict:
    """A corpus golden: 700+ nodes, `.map()` callbacks, hoisted constants.

    Read off disk rather than rebuilt, so these tests say nothing about the port --
    they are about the canonicaliser only.
    """
    return json.loads((GOLDEN / "s01" / "soc.json").read_text())


# --- fixtures shaped like the indicator layer ---------------------------------
#
# `build_indicator` ends `apply_truth_table(...).rename(band)` then
# `.where(water, 0).uint8()`; the legacy (run_15_3_1.py:411) has the same chain
# without the rename. These reproduce that shape in four nodes.


def _collapse() -> ee.Image:
    return ee.Image(0).where(ee.Image(1).eq(1), 2)


def port_indicator() -> ee.Image:
    return _collapse().rename(INDICATOR_BAND).where(ee.Image(3), 0).uint8()


def legacy_indicator() -> ee.Image:
    return _collapse().where(ee.Image(3), 0).uint8()


# --- degrees of freedom the canonical form removes -----------------------------


def _renumbered(encoded: dict) -> dict:
    """`encoded` with every scope key rewritten, in reverse insertion order.

    Rewrites the three places a key can appear: `result`, a `{"valueReference":
    key}` wrapper, and the BARE `body` key of a `functionDefinitionValue`. The
    reversal is deliberate -- it is what a canonicaliser that leaked the JSON load
    order into its traversal would trip over.
    """
    values = encoded["values"]
    order = sorted(values, key=lambda key: -int(key))
    mapping = {key: f"x{index}" for index, key in enumerate(order)}

    def walk(node):
        if isinstance(node, dict):
            return {
                name: mapping[child]
                if name in ("valueReference", "body") and isinstance(child, str)
                else walk(child)
                for name, child in node.items()
            }
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return {
        "result": mapping[encoded["result"]],
        "values": {mapping[key]: walk(values[key]) for key in order},
    }


def test_renumbering_every_scope_key_leaves_the_canonical_form_alone():
    graph = a_real_graph()

    assert render(_renumbered(graph)) == render(graph)


def test_renumbering_actually_changed_the_serialization():
    """Otherwise the test above passes by comparing a graph with itself."""
    graph = a_real_graph()

    assert json.dumps(_renumbered(graph), sort_keys=True) != json.dumps(graph, sort_keys=True)


def _hoisted(encoded: dict) -> dict:
    """`encoded` with the root's first inlined composite argument moved into `values`."""
    graph = json.loads(json.dumps(encoded))
    values = graph["values"]
    call = values[graph["result"]]["functionInvocationValue"]
    for name, argument in call["arguments"].items():
        if isinstance(argument, dict) and set(argument) != {"valueReference"}:
            values["hoisted"] = argument
            call["arguments"][name] = {"valueReference": "hoisted"}
            return graph
    raise AssertionError("the root has no inlined composite argument to hoist")


def test_hoisting_an_inlined_node_leaves_the_canonical_form_alone():
    """`ee` inlines a node used once and hoists it on the second use. Which of the
    two a graph happens to carry is presentation, not meaning."""
    graph = a_real_graph()

    assert render(_hoisted(graph)) == render(graph)


def test_hoisting_actually_changed_the_serialization():
    graph = a_real_graph()

    assert json.dumps(_hoisted(graph), sort_keys=True) != json.dumps(graph, sort_keys=True)


def _reordered(node):
    """Every dict rebuilt in reverse key order -- the JSON load order, changed."""
    if isinstance(node, dict):
        return {name: _reordered(node[name]) for name in reversed(list(node))}
    if isinstance(node, list):
        return [_reordered(item) for item in node]
    return node


def test_the_order_the_json_loaded_in_leaves_the_canonical_form_alone():
    graph = a_real_graph()

    assert render(_reordered(graph)) == render(graph)


def test_the_canonical_form_is_its_own_fixed_point():
    graph = a_real_graph()

    assert render(canonical_graph(graph)) == render(graph)


# --- differences the canonical form keeps --------------------------------------


def test_a_changed_function_name_is_visible():
    graph = a_real_graph()
    mutated = json.loads(json.dumps(graph).replace("Image.select", "Image.selfMask", 1))

    assert render(mutated) != render(graph)


def test_a_changed_argument_value_is_visible():
    before = encode(ee.Image(0).where(ee.Image(1).eq(1), 2))
    after = encode(ee.Image(0).where(ee.Image(1).eq(1), 3))

    assert render(after) != render(before)


def test_an_inserted_rename_is_visible():
    """The exact miss that made a first probe at this question report the port and
    the legacy identical: a rename's band name is INLINE in the arguments dict, not
    a node of its own, so a comparison over node function names cannot see it."""
    before = encode(ee.Image(0))
    after = encode(ee.Image(0).rename("anything"))

    assert render(after) != render(before)


def test_swapping_two_chained_calls_is_visible():
    """`.where(water, 0).uint8()` against `.uint8().where(water, 0)` -- the same
    nodes, the same count, a different graph. A comparison by population cannot see
    this one, and it is the shape `build_indicator`'s terminal line has."""
    water = ee.Image(3)
    before = encode(ee.Image(0).where(water, 0).uint8())
    after = encode(ee.Image(0).uint8().where(water, 0))

    assert render(after) != render(before)


def test_a_difference_inside_a_map_callback_is_visible():
    """A callback body is a BARE key into `values` under `functionDefinitionValue`,
    not a `{"valueReference": ...}` wrapper. A walk that does not follow it
    explicitly cannot see the whole callback subtree (tests/engine/graph.py)."""
    collection = ee.ImageCollection([ee.Image(1)])
    before = encode(collection.map(lambda image: image.add(1)).mean())
    after = encode(collection.map(lambda image: image.add(2)).mean())

    assert render(after) != render(before)


def test_a_dropped_argument_is_visible():
    graph = a_real_graph()
    mutated = json.loads(json.dumps(graph))
    call = mutated["values"][mutated["result"]]["functionInvocationValue"]
    call["arguments"].pop(sorted(call["arguments"])[0])

    assert render(mutated) != render(graph)


def _raw_function_counts(encoded: dict) -> dict[str, int]:
    """Distinct invocations per function name, counted off the RAW encoding.

    An independent implementation of what `function_name_counts` reports, written
    the way `tests/engine/graph.py:count_calls` counts: `ee` hoists a repeated
    subtree into one `values` entry, so every `functionInvocationValue` in the
    document is a distinct node.
    """
    counts: dict[str, int] = {}
    stack = [encoded]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            call = node.get("functionInvocationValue")
            if isinstance(call, dict):
                name = call["functionName"]
                counts[name] = counts.get(name, 0) + 1
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return counts


def test_the_canonical_form_keeps_every_invocation_the_raw_graph_has():
    """A canonicaliser that dropped a subtree would still compare equal to itself.

    Counted against a walk of the raw document, which reaches the `values`
    registry directly and so needs no reference resolution at all.
    """
    graph = a_real_graph()

    assert function_name_counts(graph) == _raw_function_counts(graph)


# --- the one normalisation ------------------------------------------------------


def test_the_splice_turns_the_port_graph_into_the_legacy_one():
    spliced, fired = strip_indicator_band_rename(encode(port_indicator()))

    assert fired is True
    assert render(spliced) == render(encode(legacy_indicator()))


def test_the_splice_declines_on_the_legacy_graph():
    """The normalisation is asymmetric, and has to be: a splice that fired on both
    sides would cancel a rename the legacy never had and compare nothing."""
    legacy = encode(legacy_indicator())

    spliced, fired = strip_indicator_band_rename(legacy)

    assert fired is False
    assert render(spliced) == render(legacy)


def test_the_splice_removes_the_rename_and_nothing_else():
    before = function_name_counts(encode(port_indicator()))
    spliced, fired = strip_indicator_band_rename(encode(port_indicator()))

    after = function_name_counts(spliced)

    assert fired is True
    assert after == {name: count for name, count in before.items() if name != "Image.rename"}
    assert before["Image.rename"] == 1


def test_the_splice_leaves_a_second_rename_in_place():
    """It is a splice of one named node in one position, not a rename filter."""
    image = _collapse().rename("degradation").rename(INDICATOR_BAND).where(ee.Image(3), 0).uint8()

    spliced, fired = strip_indicator_band_rename(encode(image))

    assert fired is True
    assert function_name_counts(spliced)["Image.rename"] == 1


def test_the_splice_declines_when_the_cast_moves_inside_the_water_mask():
    """`indicator.uint8().where(water, 0)` instead of `.where(water, 0).uint8()`.

    The port's cast position is part of what the goldens are meant to pin, so the
    normalisation must not follow the rename wherever it goes: it declines, the
    rename stays, and the comparison fails.
    """
    image = _collapse().rename(INDICATOR_BAND).uint8().where(ee.Image(3), 0)

    spliced, fired = strip_indicator_band_rename(encode(image))

    assert fired is False
    assert function_name_counts(spliced)["Image.rename"] == 1


def test_the_splice_declines_when_the_water_mask_is_gone():
    image = _collapse().rename(INDICATOR_BAND).uint8()

    _, fired = strip_indicator_band_rename(encode(image))

    assert fired is False


def test_the_splice_declines_on_a_differently_named_rename():
    """`run_15_3_1.py:411` left the band called `constant`. A port that renamed to
    something else has made a second, unlicensed change."""
    image = _collapse().rename("constant").where(ee.Image(3), 0).uint8()

    _, fired = strip_indicator_band_rename(encode(image))

    assert fired is False


def test_the_splice_declines_when_the_rename_takes_more_than_one_band():
    image = _collapse().rename([INDICATOR_BAND, "extra"]).where(ee.Image(3), 0).uint8()

    _, fired = strip_indicator_band_rename(encode(image))

    assert fired is False


@pytest.mark.parametrize("stem", ["land_cover", "soc", "productivity"])
def test_the_splice_declines_on_the_other_layers(stem):
    """Those layers' renames are in the legacy too, and must stay compared."""
    _, fired = strip_indicator_band_rename(
        json.loads((GOLDEN / "s01" / f"{stem}.json").read_text())
    )

    assert fired is False
