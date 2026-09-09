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
"""

from __future__ import annotations

import ee

from sdg1531.engine.indicator import build_indicator
from sdg1531.engine.land_cover import LandCoverMaps
from tests.engine.graph import (
    _call,
    _image_constant,
    _renamed_bands,
    _root,
    _selected_bands,
    _spine,
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
    return [(_call(node) or {}).get("functionName") for node in _spine(root, deref, _RECEIVER_ARG)]


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
    names = [(_call(node) or {}).get("functionName") for node in spine]
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
    assert build_indicator(productivity, land_cover, soc).serialize() == expected.serialize()


def test_the_rename_is_the_only_node_the_port_adds():
    """spec §7, and a corpus-wide EXPECTED_DIVERGENCES entry rather than a
    per-scenario one: run_15_3_1.py:411 never renames, so the legacy band is
    literally called "constant". Nothing else about the chain moves."""
    productivity, land_cover, soc = fake_inputs()
    water = land_cover.stack.select("water")
    landcover = land_cover.stack.select("degradation")

    verbatim = legacy_chain(productivity, landcover, soc).where(water, 0).uint8()
    ported = build_indicator(productivity, land_cover, soc)

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
    assert rule_rows(build_indicator(productivity, land_cover, soc)) == list(EXPECTED_ROWS)


def test_the_last_three_rules_are_the_nodata_rows():
    """run_15_3_1.py:406-408. Spelled out separately because they are the only
    rows that use `.lt(1)`, and `Rule` carries no operator field -- class 0 is
    what makes `apply_truth_table` emit `lt` (canonical.md)."""
    productivity, land_cover, soc = fake_inputs()
    assert rule_rows(build_indicator(productivity, land_cover, soc))[-3:] == [
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
    assert count_calls(build_indicator(productivity, land_cover, soc), "Image.where") == 31


def test_the_comparisons_are_nine_eq_nodes_and_three_lt_nodes():
    """Distinct-node counts, derived: the terms are `img.eq(k)` for each of the
    three operands and k in {1, 2, 3} -- 9 distinct nodes, each reused across the
    27 grid rules -- and `img.lt(1)` once per operand, 3 distinct nodes, from
    :406-408. A flipped comparison moves a node from one count to the other."""
    productivity, land_cover, soc = fake_inputs()
    image = build_indicator(productivity, land_cover, soc)
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
    assert count_calls(build_indicator(productivity, land_cover, soc), "Image.and") == 42


def test_the_water_mask_and_the_cast_sit_outside_the_collapse():
    """run_15_3_1.py:411 -- `indicator.where(water, 0).uint8()`. The mask is applied
    AFTER the 30 rules and the cast is applied AFTER the mask; the spine is the
    graph's own nesting, so this cannot be satisfied by a graph that has the right
    nodes in the wrong order."""
    productivity, land_cover, soc = fake_inputs()
    names = spine_functions(build_indicator(productivity, land_cover, soc))

    assert names[:4] == ["Image.uint8", "Image.where", "Image.rename", "Image.where"]
    assert names[-1] == "Image.constant"
    assert names.count("Image.uint8") == 1
    assert names.count("Image.where") == 31


def test_the_water_band_is_its_own_where_condition_and_writes_zero():
    """run_15_3_1.py:411: `.where(water, 0)` uses the water image as the TEST, and
    the value written is 0. `.where(water, 1)` or a test taken off another band
    both build."""
    productivity, land_cover, soc = fake_inputs()
    deref, test, value = outer_where(build_indicator(productivity, land_cover, soc))

    assert _operand_name(test, deref) == "water"
    assert value == 0


def test_indicator_band_is_renamed_and_cast_to_uint8():
    """spec §7: the legacy band is called "constant" because :411 never renames."""
    productivity, land_cover, soc = fake_inputs()
    image = build_indicator(productivity, land_cover, soc)

    assert "indicator_15_3_1" in _renamed_bands(image)
    assert count_calls(image, "Image.uint8") == 1


def test_indicator_reads_exactly_degradation_and_water_off_the_stack():
    """:374-375. `transition`, `start` and `end` are still REACHABLE -- the whole
    stack feeds both selects -- so their absence cannot be asserted; the select
    count is what pins that nothing else is read."""
    productivity, land_cover, soc = fake_inputs()
    image = build_indicator(productivity, land_cover, soc)

    assert _selected_bands(image) == {"degradation", "water"}
    assert count_calls(image, "Image.select") == 2


def test_both_bands_are_read_off_the_same_unselected_stack():
    """The python ordering trap at run_15_3_1.py:374-375: `water` is taken from the
    ORIGINAL image and only then is `landcover` rebound to
    `landcover.select("degradation")`. Swap those two lines and :374 selects "water"
    off an image that no longer carries it -- and `ee` is lazy enough to build it
    anyway, failing only on evaluation. Taking a `LandCoverMaps` removes the hazard
    only if BOTH bands are read off the stack, which is what this pins."""
    productivity, land_cover, soc = fake_inputs()
    inputs = select_inputs(build_indicator(productivity, land_cover, soc))

    assert set(inputs) == {"degradation", "water"}
    assert inputs["degradation"] == inputs["water"]
    assert _call(inputs["water"])["functionName"] == "Image.addBands"
