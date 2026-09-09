"""The three collapse tables as ordered data, checked against the AST fixture.

Rule ORDER is load-bearing: `apply_truth_table` emits one `.where()` per rule in
order, and the parity harness compares serialized graphs as plain strings.
"""

import dataclasses
import json
from itertools import product
from pathlib import Path

import pytest

from sdg1531.truth_table import (
    INDICATOR_15_3_1,
    PRODUCTIVITY_GPGV1,
    PRODUCTIVITY_GPGV2,
    Rule,
    TruthTable,
    classify,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "legacy_tables.json").read_text())


def fixture_table(name):
    (table,) = [t for t in FIXTURE["tables"] if t["name"] == name]
    return table


def as_mapping(table: TruthTable) -> dict[tuple[int, ...], int]:
    return {tuple(cls for _, cls in rule.inputs): rule.value for rule in table.rules}


PAIRS = [
    ("productivity_final", PRODUCTIVITY_GPGV2),
    ("productivity_final_GPG1", PRODUCTIVITY_GPGV1),
    ("indicator_15_3_1", INDICATOR_15_3_1),
]


@pytest.mark.parametrize("name,table", PAIRS)
def test_rules_match_the_fixture_in_source_order(name, table):
    legacy = fixture_table(name)
    ported = [[[cls for _, cls in rule.inputs], rule.value] for rule in table.rules]
    assert ported == legacy["rules"]


@pytest.mark.parametrize("name,table", PAIRS)
def test_operand_names_match_the_fixture(name, table):
    legacy_inputs = fixture_table(name)["inputs"]
    for rule in table.rules:
        assert [n for n, _ in rule.inputs] == legacy_inputs


def test_rule_counts_are_18_18_30():
    assert len(PRODUCTIVITY_GPGV2.rules) == 18
    assert len(PRODUCTIVITY_GPGV1.rules) == 18
    assert len(INDICATOR_15_3_1.rules) == 30


def test_productivity_tables_differ_in_exactly_two_cells():
    v2 = as_mapping(PRODUCTIVITY_GPGV2)
    v1 = as_mapping(PRODUCTIVITY_GPGV1)
    assert set(v2) == set(v1)
    differing = {combo for combo in v2 if v2[combo] != v1[combo]}
    assert differing == {(1, 2, 2), (2, 2, 1)}
    assert (v2[(1, 2, 2)], v1[(1, 2, 2)]) == (2, 1)
    assert (v2[(2, 2, 1)], v1[(2, 2, 1)]) == (1, 2)


@pytest.mark.parametrize("table", [PRODUCTIVITY_GPGV2, PRODUCTIVITY_GPGV1])
def test_productivity_tables_cover_their_product_exactly_once(table):
    combos = [tuple(cls for _, cls in rule.inputs) for rule in table.rules]
    assert len(combos) == len(set(combos))
    assert set(combos) == set(product((1, 2, 3), (1, 2, 3), (1, 2)))


def test_indicator_table_is_not_a_clean_product():
    """run_15_3_1.py:406-408 switch predicate: 27 eq-rules plus 3 lt(1) tail rules."""
    combos = [tuple(cls for _, cls in rule.inputs) for rule in INDICATOR_15_3_1.rules]
    assert len(combos) == len(set(combos))
    head, tail = combos[:27], combos[27:]
    assert set(head) == set(product((1, 2, 3), (1, 2, 3), (1, 2, 3)))
    assert tail == [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    # a clean product over {0,1,2,3}^3 would be 64 rules; it is 30
    assert len(combos) == 30


def test_classify_matches_the_indicator_table_over_all_64_inputs():
    table = as_mapping(INDICATOR_15_3_1)
    for combo in product(range(4), repeat=3):
        assert classify(*combo) == table.get(combo, 0), combo


def test_classify_states_one_out_all_out():
    assert classify(3, 3, 3) == 3
    assert classify(2, 2, 2) == 2
    assert classify(3, 3, 1) == 1  # one degraded sub-indicator degrades the pixel
    assert classify(0, 0, 0) == 0
    assert classify(1, 0, 0) == 1  # degraded plus two nodata is still degraded
    assert classify(0, 1, 1) == 0  # but two degraded plus one nodata is nodata


@pytest.mark.parametrize("classes", [(), (1,), (1, 2), (1, 2, 3, 1)])
def test_classify_rejects_wrong_arity(classes):
    """INDICATOR_15_3_1 has no arity but three; classify() must not answer for
    any other count rather than silently returning a plausible-looking class.
    """
    with pytest.raises(ValueError, match="exactly 3"):
        classify(*classes)


def test_band_names_record_the_indicator_rename_divergence():
    assert PRODUCTIVITY_GPGV2.band == "productivity"
    assert PRODUCTIVITY_GPGV1.band == "productivity"
    # §7: the legacy indicator chain never renames, so its band was "constant".
    assert fixture_table("indicator_15_3_1")["band"] is None
    assert INDICATOR_15_3_1.band == "indicator_15_3_1"


def test_tables_are_frozen():
    rule = INDICATOR_15_3_1.rules[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        rule.value = 9
    with pytest.raises(dataclasses.FrozenInstanceError):
        INDICATOR_15_3_1.band = "nope"
    assert isinstance(INDICATOR_15_3_1.rules, tuple)
    assert isinstance(rule.inputs, tuple)


def test_rule_and_truthtable_are_constructible_by_hand():
    table = TruthTable(rules=(Rule(inputs=(("a", 1), ("b", 0)), value=2),), band="x")
    assert table.rules[0].inputs == (("a", 1), ("b", 0))
    assert table.rules[0].value == 2
    assert table.band == "x"


def test_module_does_not_import_ee():
    """`truth_table.py` is pure data: no `ee`, no pandas, no sepal_ui (spec §4).

    Asserted over the module's own source rather than its namespace, because a
    namespace check passes for any module that imports `ee` under another name.
    """
    import ast

    import sdg1531.truth_table as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative imports in the domain"
            imported.add(node.module.split(".")[0])
    assert imported == {"__future__", "dataclasses"}
