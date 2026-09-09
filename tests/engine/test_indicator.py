"""The 15.3.1 collapse and the seven-layer seam.

Legacy: ``indicator_15_3_1`` (run_15_3_1.py:373-411) and ``compute_indicator_maps``
(:164-204).

The 30-rule chain is transcribed here TWICE, deliberately:

* :func:`legacy_chain` is the legacy expression itself, copied verbatim out of
  run_15_3_1.py:378-408. It shares no code with the port -- not
  ``truth_table.INDICATOR_15_3_1``, not ``apply_truth_table`` -- so a rule that
  moved, a comparison that flipped, an operand that swapped or a ``.where`` value
  that changed breaks the byte-identity test. That is this file re-deriving the
  plan's "byte-identical once the ``.rename()`` is put back" claim rather than
  inheriting it.
* ``LEGACY_ROWS`` restates the same 30 rows as data, and ``rule_rows()`` reads the
  emitted graph back into that shape. It catches the same faults and says WHICH
  rule moved, which a string comparison cannot.

Both blocks were extracted mechanically from the legacy file, not retyped.

Wiring, not new logic, is ``build_indicator_maps``'s risk: every builder it calls
takes single-band ``uint8`` images that would build a perfectly clean graph in the
wrong slot, and ``ee`` is lazy enough never to complain. So each equality
assertion in ``test_build_indicator_maps_wires_each_builder_to_its_own_inputs`` is
paired, in ``test_the_silent_argument_swaps_change_the_graph``, with the swapped
call it is supposed to be able to see.
"""

from __future__ import annotations

import dataclasses
import inspect
import json

import ee
import pytest

from sdg1531.engine.indicator import (
    ClassifiedLayer,
    IndicatorMaps,
    build_indicator,
    build_indicator_maps,
    serialize_maps,
)
from sdg1531.engine.integration import build_climate_collection, build_vi_collection
from sdg1531.engine.land_cover import LandCoverMaps, build_land_cover
from sdg1531.engine.productivity import (
    build_performance,
    build_productivity,
    build_state,
    build_trajectory,
)
from sdg1531.engine.soc import build_soil_organic_carbon
from sdg1531.enums import IndicatorLayer
from sdg1531.tables import DEGRADATION_LABELS, PROD_PERFORMANCE_LABELS
from tests.engine.graph import (
    _call,
    _image_constant,
    _renamed_bands,
    _root,
    _selected_bands,
    _spine,
    _spine_functions,
    _string_list_arg,
    _walk,
    count_calls,
)

# The argument each node on THIS module's chain carries its receiver in, verified
# against the encoder. `Image.constant` is deliberately absent: the walk must stop
# at the `ee.Image(0)` seed rather than step into its scalar.
_RECEIVER_ARG = {
    "Image.uint8": "value",
    "Image.where": "input",
    "Image.rename": "input",
}

# The operand images `build_indicator` is handed, named as the graph will show
# them: `productivity` and `soc` by their own `.rename()`, the land cover by the
# band the collapse selects off the stack.
_OPERANDS = ("productivity", "degradation", "soc")


def fake_land_cover() -> LandCoverMaps:
    """A five-band stand-in stack (land_cover.py:104-109).

    Every band gets a DIFFERENT constant so the serializer cannot merge two of
    them: with `ee.Image(0)` on two bands, an assertion that the collapse reads
    `degradation` could be satisfied by a graph that read the other one.
    """
    return LandCoverMaps(
        stack=ee.Image(2)
        .rename("degradation")
        .addBands(ee.Image(1020).rename("transition"))
        .addBands(ee.Image(10).rename("start"))
        .addBands(ee.Image(20).rename("end"))
        .addBands(ee.Image(9).rename("water"))
    )


def fake_inputs():
    """`(productivity, land_cover, soc)` for the collapse tests."""
    return (
        ee.Image(1).rename("productivity"),
        fake_land_cover(),
        ee.Image(3).rename("soc"),
    )


def legacy_chain(productivity, landcover, soc):
    """run_15_3_1.py:378-408, verbatim. Shares no code with the port."""
    return (
        ee.Image(0)
        .where(productivity.eq(3).And(landcover.eq(3)).And(soc.eq(3)), 3)
        .where(productivity.eq(3).And(landcover.eq(3)).And(soc.eq(2)), 3)
        .where(productivity.eq(3).And(landcover.eq(3)).And(soc.eq(1)), 1)
        .where(productivity.eq(3).And(landcover.eq(2)).And(soc.eq(3)), 3)
        .where(productivity.eq(3).And(landcover.eq(2)).And(soc.eq(2)), 3)
        .where(productivity.eq(3).And(landcover.eq(2)).And(soc.eq(1)), 1)
        .where(productivity.eq(3).And(landcover.eq(1)).And(soc.eq(3)), 1)
        .where(productivity.eq(3).And(landcover.eq(1)).And(soc.eq(2)), 1)
        .where(productivity.eq(3).And(landcover.eq(1)).And(soc.eq(1)), 1)
        .where(productivity.eq(2).And(landcover.eq(3)).And(soc.eq(3)), 3)
        .where(productivity.eq(2).And(landcover.eq(3)).And(soc.eq(2)), 3)
        .where(productivity.eq(2).And(landcover.eq(3)).And(soc.eq(1)), 1)
        .where(productivity.eq(2).And(landcover.eq(2)).And(soc.eq(3)), 3)
        .where(productivity.eq(2).And(landcover.eq(2)).And(soc.eq(2)), 2)
        .where(productivity.eq(2).And(landcover.eq(2)).And(soc.eq(1)), 1)
        .where(productivity.eq(2).And(landcover.eq(1)).And(soc.eq(3)), 1)
        .where(productivity.eq(2).And(landcover.eq(1)).And(soc.eq(2)), 1)
        .where(productivity.eq(2).And(landcover.eq(1)).And(soc.eq(1)), 1)
        .where(productivity.eq(1).And(landcover.eq(3)).And(soc.eq(3)), 1)
        .where(productivity.eq(1).And(landcover.eq(3)).And(soc.eq(2)), 1)
        .where(productivity.eq(1).And(landcover.eq(3)).And(soc.eq(1)), 1)
        .where(productivity.eq(1).And(landcover.eq(2)).And(soc.eq(3)), 1)
        .where(productivity.eq(1).And(landcover.eq(2)).And(soc.eq(2)), 1)
        .where(productivity.eq(1).And(landcover.eq(2)).And(soc.eq(1)), 1)
        .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(3)), 1)
        .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(2)), 1)
        .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(1)), 1)
        .where(productivity.eq(1).And(landcover.lt(1)).And(soc.lt(1)), 1)
        .where(productivity.lt(1).And(landcover.eq(1)).And(soc.lt(1)), 1)
        .where(productivity.lt(1).And(landcover.lt(1)).And(soc.eq(1)), 1)
    )


# run_15_3_1.py:379-408 as data: one row per `.where()`, in source order, each
# row `(productivity term, landcover term, soc term, value)` and each term
# `(operator, class)`. Extracted from the legacy file with a regex, not retyped;
# the three `("lt", 1)` terms are :406-408's nodata rows.
LEGACY_ROWS = (
    (("eq", 3), ("eq", 3), ("eq", 3), 3),
    (("eq", 3), ("eq", 3), ("eq", 2), 3),
    (("eq", 3), ("eq", 3), ("eq", 1), 1),
    (("eq", 3), ("eq", 2), ("eq", 3), 3),
    (("eq", 3), ("eq", 2), ("eq", 2), 3),
    (("eq", 3), ("eq", 2), ("eq", 1), 1),
    (("eq", 3), ("eq", 1), ("eq", 3), 1),
    (("eq", 3), ("eq", 1), ("eq", 2), 1),
    (("eq", 3), ("eq", 1), ("eq", 1), 1),
    (("eq", 2), ("eq", 3), ("eq", 3), 3),
    (("eq", 2), ("eq", 3), ("eq", 2), 3),
    (("eq", 2), ("eq", 3), ("eq", 1), 1),
    (("eq", 2), ("eq", 2), ("eq", 3), 3),
    (("eq", 2), ("eq", 2), ("eq", 2), 2),
    (("eq", 2), ("eq", 2), ("eq", 1), 1),
    (("eq", 2), ("eq", 1), ("eq", 3), 1),
    (("eq", 2), ("eq", 1), ("eq", 2), 1),
    (("eq", 2), ("eq", 1), ("eq", 1), 1),
    (("eq", 1), ("eq", 3), ("eq", 3), 1),
    (("eq", 1), ("eq", 3), ("eq", 2), 1),
    (("eq", 1), ("eq", 3), ("eq", 1), 1),
    (("eq", 1), ("eq", 2), ("eq", 3), 1),
    (("eq", 1), ("eq", 2), ("eq", 2), 1),
    (("eq", 1), ("eq", 2), ("eq", 1), 1),
    (("eq", 1), ("eq", 1), ("eq", 3), 1),
    (("eq", 1), ("eq", 1), ("eq", 2), 1),
    (("eq", 1), ("eq", 1), ("eq", 1), 1),
    (("eq", 1), ("lt", 1), ("lt", 1), 1),
    (("lt", 1), ("eq", 1), ("lt", 1), 1),
    (("lt", 1), ("lt", 1), ("eq", 1), 1),
)

EXPECTED_ROWS = tuple(
    (tuple((name, op, cls) for name, (op, cls) in zip(_OPERANDS, terms, strict=True)), value)
    for *terms, value in LEGACY_ROWS
)


# --- graph decoding -----------------------------------------------------------


def spine_functions(image):
    """The function names on the image's receiver spine, outermost first.

    Spine-based rather than count-based: the serializer collapses structurally
    identical subtrees, so a count cannot see a duplicated node, but the spine is
    the graph's own nesting and reordering two chained calls reorders it.
    """
    deref, _graph, root = _root(image)
    return _spine_functions(root, deref, _RECEIVER_ARG)


def _operand_name(node, deref):
    """The band a rule's operand image is known by."""
    call = _call(node)
    name = call.get("functionName") if call else None
    if name == "Image.select":
        return _string_list_arg(deref(call["arguments"]["bandSelectors"]), deref)[0]
    if name == "Image.rename":
        return _string_list_arg(deref(call["arguments"]["names"]), deref)[0]
    raise AssertionError(f"operand is neither a select nor a rename: {name}")


def _term(node, deref):
    """`(operand name, operator, class)` for one `img.eq(k)` / `img.lt(k)` term."""
    call = _call(node)
    name = call.get("functionName") if call else None
    if name not in ("Image.eq", "Image.lt"):
        raise AssertionError(f"rule term is not a comparison: {name}")
    return (
        _operand_name(deref(call["arguments"]["image1"]), deref),
        name.removeprefix("Image."),
        _image_constant(deref(call["arguments"]["image2"]), deref),
    )


def _terms(node, deref):
    """A predicate's AND terms, left to right. `.And()` nests left-associatively."""
    call = _call(node)
    if call and call.get("functionName") == "Image.and":
        return [
            *_terms(deref(call["arguments"]["image1"]), deref),
            _term(deref(call["arguments"]["image2"]), deref),
        ]
    return [_term(node, deref)]


def rule_rows(image):
    """The collapse's rules, in emitted order, decoded into ``EXPECTED_ROWS`` shape.

    Everything INSIDE the `.rename()` is the rule chain; the `.where(water, 0)`
    and the `.uint8()` sit outside it and are read by their own tests.
    """
    deref, _graph, root = _root(image)
    spine = _spine(root, deref, _RECEIVER_ARG)
    names = _spine_functions(root, deref, _RECEIVER_ARG)
    assert names.count("Image.rename") == 1, names
    inner = spine[names.index("Image.rename") + 1 :]

    seed = inner[-1]
    assert (_call(seed) or {}).get("functionName") == "Image.constant"
    assert _image_constant(seed, deref) == 0, "the chain must start from ee.Image(0)"

    rows = []
    for node in inner[:-1]:
        call = _call(node)
        assert call is not None and call["functionName"] == "Image.where", call
        rows.append(
            (
                tuple(_terms(deref(call["arguments"]["test"]), deref)),
                _image_constant(deref(call["arguments"]["value"]), deref),
            )
        )
    return list(reversed(rows))  # the spine is outermost-first


def select_inputs(image):
    """`{band: the resolved node it is selected off}` for every `Image.select`."""
    deref, graph, root = _root(image)
    found = {}
    for node in _walk(root, deref, graph):
        call = _call(node)
        if call is None or call.get("functionName") != "Image.select":
            continue
        band = _string_list_arg(deref(call["arguments"]["bandSelectors"]), deref)[0]
        found[band] = deref(call["arguments"]["input"])
    return found


# Nodes that hand their receiver's band list straight through, and the argument
# carrying that receiver. Read off the encoder, like `_RECEIVER_ARG`.
_BAND_PRESERVING = {
    "Image.uint8": "value",
    "Image.uint16": "value",
    "Image.where": "input",
}


def output_bands(image):
    """The band names `image` really carries, decoded from its own graph.

    NOT the graph-wide set of `.rename()` targets. That set is a population over the
    whole upstream subgraph: for the indicator image it is every rename in the
    corpus -- 17 names, including all seven layer bands -- so `band in renames`
    there is satisfied by any band whatsoever. This walks only the band-SHAPING
    nodes, the ones that decide the output band list.

    It RAISES on a node it does not know rather than returning what it has so far.
    A decoder that silently answered "no bands" would make its caller vacuous, which
    is the defect this function exists to fix.
    """
    deref, _graph, root = _root(image)

    def bands(node):
        node = deref(node)
        call = _call(node)
        if call is None:
            raise AssertionError(f"output_bands reached a non-call node: {node!r}")
        name, args = call["functionName"], call.get("arguments", {})
        if name == "Image.rename":
            return _string_list_arg(deref(args["names"]), deref)
        if name == "Image.select":
            return _string_list_arg(deref(args["bandSelectors"]), deref)
        if name == "Image.addBands":
            # the `names`/`overwrite` overloads would rewrite the band list; no
            # builder uses them, and a future one must extend this decoder.
            assert set(args) == {"dstImg", "srcImg"}, sorted(args)
            return bands(args["dstImg"]) + bands(args["srcImg"])
        if name == "Image.constant":
            return ["constant"]
        if name in _BAND_PRESERVING:
            return bands(args[_BAND_PRESERVING[name]])
        raise AssertionError(f"output_bands cannot decode {name!r}; extend the table")

    return bands(root)


def outer_where(image):
    """`(deref, test node, value)` of the OUTERMOST `Image.where` -- the water mask.

    `deref` comes back with the nodes because it closes over THIS image's `values`
    registry; resolving a node against another encoding's registry would read the
    wrong entry, or raise.
    """
    deref, _graph, root = _root(image)
    for node in _spine(root, deref, _RECEIVER_ARG):
        call = _call(node)
        if call is not None and call.get("functionName") == "Image.where":
            value = _image_constant(deref(call["arguments"]["value"]), deref)
            return deref, deref(call["arguments"]["test"]), value
    raise AssertionError("no Image.where on the spine")


# --- the collapse: the chain itself -------------------------------------------


def test_the_collapse_is_the_legacy_chain_with_the_rename_put_back():
    """The byte-identity claim, re-derived here rather than inherited.

    ``legacy_chain`` is run_15_3_1.py:378-408 copied verbatim and reaches `ee`
    through none of the port's code. Insert the one deliberate node -- the
    `.rename()` of spec §7 -- where the port puts it, and the two serialize to the
    same bytes. Any rule reordered, any `eq`/`lt` flipped, any operand swapped and
    any `.where` value changed breaks this.
    """
    productivity, land_cover, soc = fake_inputs()
    water = land_cover.stack.select("water")  # :374, off the ORIGINAL stack
    landcover = land_cover.stack.select("degradation")  # :375

    expected = (
        legacy_chain(productivity, landcover, soc)
        .rename("indicator_15_3_1")
        .where(water, 0)
        .uint8()
    )
    assert (
        build_indicator(productivity=productivity, land_cover=land_cover, soc=soc).serialize()
        == expected.serialize()
    )


def test_the_rename_is_the_only_node_the_port_adds():
    """spec §7, and a corpus-wide EXPECTED_DIVERGENCES entry rather than a
    per-scenario one: run_15_3_1.py:411 never renames, so the legacy band is
    literally called "constant". Nothing else about the chain moves."""
    productivity, land_cover, soc = fake_inputs()
    water = land_cover.stack.select("water")
    landcover = land_cover.stack.select("degradation")

    verbatim = legacy_chain(productivity, landcover, soc).where(water, 0).uint8()
    ported = build_indicator(productivity=productivity, land_cover=land_cover, soc=soc)

    assert ported.serialize() != verbatim.serialize()
    assert _renamed_bands(ported) - _renamed_bands(verbatim) == {"indicator_15_3_1"}
    assert _renamed_bands(verbatim) - _renamed_bands(ported) == set()


def test_the_thirty_rules_are_emitted_in_legacy_order_with_their_own_operators():
    """The same 30 rows as the byte-identity test, read back out of the graph so a
    failure names the rule. Order, operand position, operator and value are all in
    the compared value: reordering two rules, reading `transition` instead of
    `degradation`, turning an `lt` into an `eq` or changing a `.where` value each
    change exactly one element of it."""
    productivity, land_cover, soc = fake_inputs()
    assert rule_rows(
        build_indicator(productivity=productivity, land_cover=land_cover, soc=soc)
    ) == list(EXPECTED_ROWS)


def test_the_last_three_rules_are_the_nodata_rows():
    """run_15_3_1.py:406-408. Spelled out separately because they are the only
    rows that use `.lt(1)`, and `Rule` carries no operator field -- class 0 is
    what makes `apply_truth_table` emit `lt` (canonical.md)."""
    productivity, land_cover, soc = fake_inputs()
    assert rule_rows(build_indicator(productivity=productivity, land_cover=land_cover, soc=soc))[
        -3:
    ] == [
        ((("productivity", "eq", 1), ("degradation", "lt", 1), ("soc", "lt", 1)), 1),
        ((("productivity", "lt", 1), ("degradation", "eq", 1), ("soc", "lt", 1)), 1),
        ((("productivity", "lt", 1), ("degradation", "lt", 1), ("soc", "eq", 1)), 1),
    ]


# --- the collapse: shape ------------------------------------------------------


def test_indicator_has_thirty_rule_wheres_plus_the_water_where():
    """run_15_3_1.py:379-408 plus :411.

    A distinct-node count, so it needs a derivation: every `.where()` takes the
    previous one as its receiver, so no two are structurally equal and CSE cannot
    merge any of them. 30 + 1 = 31.
    """
    productivity, land_cover, soc = fake_inputs()
    assert (
        count_calls(
            build_indicator(productivity=productivity, land_cover=land_cover, soc=soc),
            "Image.where",
        )
        == 31
    )


def test_the_comparisons_are_nine_eq_nodes_and_three_lt_nodes():
    """Distinct-node counts, derived: the terms are `img.eq(k)` for each of the
    three operands and k in {1, 2, 3} -- 9 distinct nodes, each reused across the
    27 grid rules -- and `img.lt(1)` once per operand, 3 distinct nodes, from
    :406-408. A flipped comparison moves a node from one count to the other."""
    productivity, land_cover, soc = fake_inputs()
    image = build_indicator(productivity=productivity, land_cover=land_cover, soc=soc)
    assert count_calls(image, "Image.eq") == 9
    assert count_calls(image, "Image.lt") == 3


def test_every_rule_ands_three_terms_and_shares_the_twelve_it_can():
    """Distinct-node count, derived from the CSE the nesting allows: the inner
    two-term node depends on only two of the three operands, so the 27 grid rules
    share 9 of them (one per pair) and the three nodata rows -- whose pairs are all
    unlike the grid's -- add 3 more; the outer node is unique per rule, 30 of them.
    12 + 30 = 42.

    It pins the number of AND terms per rule, not their associativity. Mutation
    testing showed that nesting `.And()` to the RIGHT also yields 42: this table is
    symmetric enough that grouping the last two operands shares just as many nodes
    as grouping the first two. Associativity is pinned by
    `test_the_thirty_rules_are_emitted_in_legacy_order_with_their_own_operators`,
    whose decoder walks the actual nesting, and by the byte-identity test; both go
    red on that mutation. What this count does catch is a rule added or dropped
    (41 or 43) and a term dropped from every predicate (12).
    """
    productivity, land_cover, soc = fake_inputs()
    assert (
        count_calls(
            build_indicator(productivity=productivity, land_cover=land_cover, soc=soc), "Image.and"
        )
        == 42
    )


def test_the_water_mask_and_the_cast_sit_outside_the_collapse():
    """run_15_3_1.py:411 -- `indicator.where(water, 0).uint8()`. The mask is applied
    AFTER the 30 rules and the cast is applied AFTER the mask; the spine is the
    graph's own nesting, so this cannot be satisfied by a graph that has the right
    nodes in the wrong order."""
    productivity, land_cover, soc = fake_inputs()
    names = spine_functions(
        build_indicator(productivity=productivity, land_cover=land_cover, soc=soc)
    )

    assert names[:4] == ["Image.uint8", "Image.where", "Image.rename", "Image.where"]
    assert names[-1] == "Image.constant"
    assert names.count("Image.uint8") == 1
    assert names.count("Image.where") == 31


def test_the_water_band_is_its_own_where_condition_and_writes_zero():
    """run_15_3_1.py:411: `.where(water, 0)` uses the water image as the TEST, and
    the value written is 0. `.where(water, 1)` or a test taken off another band
    both build."""
    productivity, land_cover, soc = fake_inputs()
    deref, test, value = outer_where(
        build_indicator(productivity=productivity, land_cover=land_cover, soc=soc)
    )

    assert _operand_name(test, deref) == "water"
    assert value == 0


def test_build_indicator_takes_its_three_images_by_keyword_only():
    """The guard `build_productivity` already carries (productivity.py:512-517).

    `productivity` and `soc` are both single-band 3-class uint8, INDICATOR_15_3_1 is
    not symmetric in them (:385-387 against :394-396), and `ee` is lazy -- so a
    positional swap builds a clean graph and misclassifies at evaluation time.
    Keyword-only turns that into a TypeError at the call site instead.
    """
    productivity, land_cover, soc = fake_inputs()
    kinds = [p.kind for p in inspect.signature(build_indicator).parameters.values()]
    assert kinds == [inspect.Parameter.KEYWORD_ONLY] * 3

    with pytest.raises(TypeError, match="takes 0 positional arguments"):
        build_indicator(productivity, land_cover, soc)


def test_indicator_band_is_renamed_and_cast_to_uint8():
    """spec §7: the legacy band is called "constant" because :411 never renames."""
    productivity, land_cover, soc = fake_inputs()
    image = build_indicator(productivity=productivity, land_cover=land_cover, soc=soc)

    assert "indicator_15_3_1" in _renamed_bands(image)
    assert count_calls(image, "Image.uint8") == 1


def test_indicator_reads_exactly_degradation_and_water_off_the_stack():
    """:374-375. `transition`, `start` and `end` are still REACHABLE -- the whole
    stack feeds both selects -- so their absence cannot be asserted; the select
    count is what pins that nothing else is read."""
    productivity, land_cover, soc = fake_inputs()
    image = build_indicator(productivity=productivity, land_cover=land_cover, soc=soc)

    assert _selected_bands(image) == {"degradation", "water"}
    assert count_calls(image, "Image.select") == 2


def test_both_bands_are_read_off_the_same_unselected_stack():
    """The python ordering trap at run_15_3_1.py:374-375: `water` is taken from the
    ORIGINAL image and only then is `landcover` rebound to
    `landcover.select("degradation")`. Swap those two lines and :374 selects "water"
    off an image that no longer carries it -- and `ee` is lazy enough to build it
    anyway, failing only on evaluation. Taking a `LandCoverMaps` removes the hazard
    only if BOTH bands are read off the stack, which is what this pins.

    `is` rather than `==` because node identity is the claim. It is not the stronger
    check it looks like: the serializer does CSE by structural equality, so two
    separately-built but identical stacks collapse to ONE `values` entry and `deref`
    hands back the same object for both. Measured -- `is` and `==` agree on one
    shared stack, on two identical stacks and on two different ones. The spelling
    states the intent; the strength comes from `set(inputs)` and the `addBands`
    check below.
    """
    productivity, land_cover, soc = fake_inputs()
    inputs = select_inputs(
        build_indicator(productivity=productivity, land_cover=land_cover, soc=soc)
    )

    assert set(inputs) == {"degradation", "water"}
    assert inputs["degradation"] is inputs["water"]
    assert _call(inputs["water"])["functionName"] == "Image.addBands"


# --- build_indicator_maps: the wiring -----------------------------------------


@pytest.fixture
def maps(resolved, ctx):
    return build_indicator_maps(resolved, ctx)


def leaf_builds(resolved, ctx):
    """Every intermediate `build_indicator_maps` builds, rebuilt independently here
    in run_15_3_1.py:171-202's own order."""
    climate = build_climate_collection(resolved, ctx)  # :171
    vi = build_vi_collection(resolved, ctx)  # :172
    trajectory = build_trajectory(resolved, vi, climate)  # :173-175
    performance = build_performance(resolved, ctx, vi)  # :176-178
    state = build_state(resolved, vi)  # :179
    land_cover = build_land_cover(resolved, ctx)  # :182
    soc = build_soil_organic_carbon(resolved, ctx)  # :183
    productivity = build_productivity(  # :184-197
        resolved, trajectory=trajectory, state=state, performance=performance
    )
    return {
        "climate": climate,
        "vi": vi,
        "trajectory": trajectory,
        "performance": performance,
        "state": state,
        "land_cover": land_cover,
        "soc": soc,
        "productivity": productivity,
    }


def test_build_indicator_maps_wires_each_builder_to_its_own_inputs(resolved, ctx, maps):
    """run_15_3_1.py:164-204. Every output is compared against the same builder
    called with the same inputs, so a seam that fed one builder another builder's
    image shows up as a different graph."""
    leaves = leaf_builds(resolved, ctx)

    assert maps.productivity_trend.serialize() == leaves["trajectory"].serialize()
    assert maps.productivity_state.serialize() == leaves["state"].serialize()
    assert maps.productivity_performance.serialize() == leaves["performance"].serialize()
    assert maps.land_cover.stack.serialize() == leaves["land_cover"].stack.serialize()
    assert maps.soc.serialize() == leaves["soc"].serialize()
    assert maps.productivity.serialize() == leaves["productivity"].serialize()
    assert (
        maps.indicator.serialize()
        == build_indicator(
            productivity=leaves["productivity"],
            land_cover=leaves["land_cover"],
            soc=leaves["soc"],
        ).serialize()
    )


def test_the_silent_argument_swaps_change_the_graph(resolved, ctx):
    """What makes the equalities above evidence rather than tautology.

    Each swap below builds a perfectly clean graph -- `ee` is lazy and the operands
    are all single-band uint8 images -- and computes the wrong classes. If any of
    these three comparisons were `==`, the corresponding equality assertion could
    not see the swap it is there to catch.
    """
    leaves = leaf_builds(resolved, ctx)

    # build_trajectory(r, vi, climate): NDVI_TREND never reads `climate`, so a swap
    # runs the Kendall trend over precipitation instead of the vegetation index.
    assert (
        build_trajectory(resolved, leaves["climate"], leaves["vi"]).serialize()
        != leaves["trajectory"].serialize()
    )

    # build_productivity's state/performance are keyword-only precisely because the
    # legacy signature and its only call site are (trajectory, PERFORMANCE, STATE)
    # -- productivity.py:252 and run_15_3_1.py:185-190 -- while the port's rule
    # order is (trajectory, STATE, PERFORMANCE).
    assert (
        build_productivity(
            resolved,
            trajectory=leaves["trajectory"],
            state=leaves["performance"],
            performance=leaves["state"],
        ).serialize()
        != leaves["productivity"].serialize()
    )

    # build_indicator(productivity=productivity, land_cover=land_cover, soc=soc): both are 3-class uint8 images
    # and INDICATOR_15_3_1 is not symmetric in them (:385-387 against :394-396).
    assert (
        build_indicator(
            productivity=leaves["soc"],
            land_cover=leaves["land_cover"],
            soc=leaves["productivity"],
        ).serialize()
        != build_indicator(
            productivity=leaves["productivity"],
            land_cover=leaves["land_cover"],
            soc=leaves["soc"],
        ).serialize()
    )


def test_maps_carry_the_very_resolved_spec_they_were_handed(resolved, ctx):
    """Task 15's `fetch_transition_areas` / `fetch_areas_by_land_cover` decode class
    codes off `maps.resolved`."""
    assert build_indicator_maps(resolved, ctx).resolved is resolved


def test_resolved_is_the_first_field_and_the_seven_outputs_follow(maps):
    """Field ORDER is load-bearing, not cosmetic: `resolved` is first so Task 15
    reads it positionally-independently of the seven images, and the seven follow in
    spec §8 order."""
    assert [field.name for field in dataclasses.fields(IndicatorMaps)] == [
        "resolved",
        "land_cover",
        "soc",
        "productivity",
        "productivity_trend",
        "productivity_state",
        "productivity_performance",
        "indicator",
    ]


def test_indicator_maps_is_frozen(maps):
    with pytest.raises(dataclasses.FrozenInstanceError, match="cannot assign to field 'soc'"):
        maps.soc = ee.Image(0)


def test_classified_layer_is_frozen(maps):
    layer = maps.layers()[IndicatorLayer.SOC]
    with pytest.raises(dataclasses.FrozenInstanceError, match="cannot assign to field 'band'"):
        layer.band = "other"


# --- the seven-layer seam -----------------------------------------------------


def test_layers_returns_exactly_seven_entries_in_spec_order(maps):
    """spec §8 table order. Asserted as a LIST: a mapping with the right seven keys
    in a different order passes an equality on `set(layers)`, and one that keyed two
    layers under the same id passes a `len(...) == 7` written against a set."""
    layers = maps.layers()
    assert list(layers) == [
        IndicatorLayer.LAND_COVER,
        IndicatorLayer.SOC,
        IndicatorLayer.PRODUCTIVITY,
        IndicatorLayer.PRODUCTIVITY_TREND,
        IndicatorLayer.PRODUCTIVITY_STATE,
        IndicatorLayer.PRODUCTIVITY_PERFORMANCE,
        IndicatorLayer.INDICATOR_15_3_1,
    ]
    assert len(layers) == 7


def test_every_layer_is_keyed_by_its_own_id_and_labelled_by_its_value(maps):
    for key, layer in maps.layers().items():
        assert isinstance(layer, ClassifiedLayer)
        assert layer.id is key
        assert layer.label == key.value
        assert isinstance(layer.image, ee.Image)


def test_each_layer_carries_its_own_image(maps):
    """The seven `.image`s are the seven outputs, each in its own slot -- the
    mistake a keyed mapping cannot show is two entries pointing at one image."""
    layers = maps.layers()
    images = {
        IndicatorLayer.LAND_COVER: maps.land_cover.stack,
        IndicatorLayer.SOC: maps.soc,
        IndicatorLayer.PRODUCTIVITY: maps.productivity,
        IndicatorLayer.PRODUCTIVITY_TREND: maps.productivity_trend,
        IndicatorLayer.PRODUCTIVITY_STATE: maps.productivity_state,
        IndicatorLayer.PRODUCTIVITY_PERFORMANCE: maps.productivity_performance,
        IndicatorLayer.INDICATOR_15_3_1: maps.indicator,
    }
    for key, image in images.items():
        assert layers[key].image is image
    assert len({id(layer.image) for layer in layers.values()}) == 7


def test_layer_bands_match_the_export_table(maps):
    """spec §8, the EXPORT vocabulary. Trend and state carry the 3-class band; the
    5-level band `indicator_n_category_label` selected (run_15_3_1.py:437-441) stays
    the STATISTICS vocabulary and lives in `stats/requests.py`'s `_STATS_BAND` --
    see the module docstring's EXPECTED_DIVERGENCES note 4."""
    assert {key: layer.band for key, layer in maps.layers().items()} == {
        IndicatorLayer.LAND_COVER: "degradation",
        IndicatorLayer.SOC: "soc",
        IndicatorLayer.PRODUCTIVITY: "productivity",
        IndicatorLayer.PRODUCTIVITY_TREND: "trajectory",
        IndicatorLayer.PRODUCTIVITY_STATE: "state",
        IndicatorLayer.PRODUCTIVITY_PERFORMANCE: "performance",
        IndicatorLayer.INDICATOR_15_3_1: "indicator_15_3_1",
    }


def test_every_named_band_really_exists_in_its_own_image(maps):
    """`ClassifiedLayer.band` is a promise consumers act on with
    `layer.image.select(layer.band)`, so it is checked against the image's OWN band
    list, decoded from its band-shaping nodes.

    The earlier spelling of this test asked `band in _renamed_bands(image)`, a union
    over the whole upstream subgraph. That is far weaker than it reads: the
    indicator image's union is every rename in the corpus, so any of the seven layer
    bands satisfied it, and both reviewers landed a mislabelled band that this test
    waved through while only `test_layer_bands_match_the_export_table` -- itself a
    hardcoded mirror of the implementation -- objected.
    """
    for key, layer in maps.layers().items():
        assert layer.band in output_bands(layer.image), key


def test_the_seven_images_carry_exactly_the_bands_the_builders_name(maps):
    """The other half of the band contract: not just that `layer.band` is present,
    but what else rides with it. Trend and state are the two-band images whose band
    0 is the 5-class one the statistics path selects; the rest are single-band."""
    assert {key: output_bands(layer.image) for key, layer in maps.layers().items()} == {
        IndicatorLayer.LAND_COVER: ["degradation", "transition", "start", "end", "water"],
        IndicatorLayer.SOC: ["soc"],
        IndicatorLayer.PRODUCTIVITY: ["productivity"],
        IndicatorLayer.PRODUCTIVITY_TREND: ["trajectory_5_levels", "trajectory"],
        IndicatorLayer.PRODUCTIVITY_STATE: ["state_5_levels", "state"],
        IndicatorLayer.PRODUCTIVITY_PERFORMANCE: ["performance"],
        IndicatorLayer.INDICATOR_15_3_1: ["indicator_15_3_1"],
    }


def test_only_performance_uses_the_three_class_labels(maps):
    """`pm.prod_performance_class` has no "Improved" (tables.py:99-101); every
    other layer is on the 4-entry degradation legend."""
    layers = maps.layers()
    assert layers[IndicatorLayer.PRODUCTIVITY_PERFORMANCE].labels == PROD_PERFORMANCE_LABELS
    for key, layer in layers.items():
        if key is not IndicatorLayer.PRODUCTIVITY_PERFORMANCE:
            assert layer.labels == DEGRADATION_LABELS, key


def test_there_is_no_export_layers_method():
    """spec §4: layers() is the single seam -- map layers, export sources and the
    statistics layer picker all iterate it."""
    assert not hasattr(IndicatorMaps, "export_layers")


# --- serialization ------------------------------------------------------------


def test_serialize_maps_is_keyed_by_the_spec_layer_ids(maps):
    payload = serialize_maps(maps)
    assert list(payload) == [
        "land_cover",
        "soc",
        "productivity",
        "productivity_trend",
        "productivity_state",
        "productivity_performance",
        "indicator_15_3_1",
    ]


def test_every_serialize_key_is_its_layer_s_own_id(maps):
    """The key is `layer.id.name.lower()`, which is the §8 "Layer id" column and so
    equals `layer.id.value` for all seven. Pinned so the two spellings cannot drift
    apart silently."""
    for key, layer in zip(serialize_maps(maps), maps.layers().values(), strict=True):
        assert key == layer.id.name.lower() == layer.id.value


def test_serialize_maps_encodes_the_whole_image_not_the_named_band(maps):
    """§12 Tier 4 compares these strings old-vs-new, and the legacy assigned WHOLE
    images to its seven output traits (run_15_3_1.py:173-202). Encoding
    `layer.image.select(layer.band)` instead would silently change every trend and
    state comparison, since those images carry two bands."""
    payload = serialize_maps(maps)
    for key, layer in zip(payload, maps.layers().values(), strict=True):
        assert payload[key] == ee.serializer.toJSON(layer.image)
        assert json.loads(payload[key])["result"]

    assert payload["productivity_trend"] == ee.serializer.toJSON(maps.productivity_trend)
    assert payload["productivity_trend"] != ee.serializer.toJSON(
        maps.productivity_trend.select("trajectory")
    )


def test_serialization_is_stable_across_rebuilds(resolved, ctx):
    """The parity harness compares these as plain strings (§12 Tier 4), so a graph
    that carried a counter or a timestamp would make every run differ."""
    assert serialize_maps(build_indicator_maps(resolved, ctx)) == serialize_maps(
        build_indicator_maps(resolved, ctx)
    )
