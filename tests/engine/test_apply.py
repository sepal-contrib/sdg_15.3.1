"""One compiler for all three `.where()` collapses.

Parity is the whole point: the emitted chain must be node-identical to the
legacy hand-written one (productivity.py:257-332, :342-417,
run_15_3_1.py:377-409), including the left-associative `.And()` nesting and the
rule order.
"""

import json

import ee
import pytest

from sdg1531.engine.apply import apply_truth_table
from sdg1531.truth_table import PRODUCTIVITY_GPGV2, Rule, TruthTable


def count_calls(node, name):
    """Count functionInvocationValue nodes for `name` anywhere in a graph."""
    if isinstance(node, dict):
        found = int(node.get("functionInvocationValue", {}).get("functionName") == name)
        return found + sum(count_calls(value, name) for value in node.values())
    if isinstance(node, list):
        return sum(count_calls(value, name) for value in node)
    return 0


def test_two_rule_chain_is_node_identical_to_the_hand_written_one(ee_offline):
    a = ee.Image(7)
    b = ee.Image(8)
    table = TruthTable(
        rules=(
            Rule(inputs=(("a", 1), ("b", 2)), value=3),
            Rule(inputs=(("a", 0), ("b", 1)), value=1),
        ),
        band="demo",
    )
    expected = (
        ee.Image(0).where(a.eq(1).And(b.eq(2)), 3).where(a.lt(1).And(b.eq(1)), 1).rename("demo")
    )
    assert apply_truth_table([a, b], table, "demo").serialize() == expected.serialize()


def test_single_operand_rule_emits_no_And(ee_offline):
    a = ee.Image(7)
    table = TruthTable(rules=(Rule(inputs=(("a", 2),), value=5),), band="demo")
    expected = ee.Image(0).where(a.eq(2), 5).rename("demo")
    built = apply_truth_table([a], table, "demo")
    assert built.serialize() == expected.serialize()
    assert count_calls(json.loads(built.serialize()), "Image.and") == 0


def test_class_zero_emits_lt_one_not_eq_zero(ee_offline):
    a = ee.Image(7)
    table = TruthTable(rules=(Rule(inputs=(("a", 0),), value=1),), band="demo")
    built = apply_truth_table([a], table, "demo")
    graph = json.loads(built.serialize())
    assert count_calls(graph, "Image.lt") == 1
    assert count_calls(graph, "Image.eq") == 0


def test_productivity_chain_has_one_where_per_rule(ee_offline):
    trajectory = ee.Image(1).rename("trajectory")
    state = ee.Image(2).rename("state")
    performance = ee.Image(3).rename("performance")
    built = apply_truth_table([trajectory, state, performance], PRODUCTIVITY_GPGV2, "productivity")
    graph = json.loads(built.serialize())
    assert count_calls(graph, "Image.where") == 18
    # Not 18 * 2: ee's serializer does common-subexpression elimination by structural
    # equality (verified directly — two separately-built `a.eq(1).And(b.eq(1))` chains
    # encode to one shared node, referenced twice). PRODUCTIVITY_GPGV2's 18 rules are
    # every (trajectory, state) pair in {1,2,3}^2 crossed with performance in {1,2}, so
    # each of the 9 first-level `trajectory.eq(t).And(state.eq(s))` nodes is built twice
    # (once per performance value) and collapses to one shared node: 9 first-level nodes,
    # not 18. The second-level `.And(performance.eq(p))` stays 18-wide, since (t, s, p) is
    # unique per rule. 9 + 18 = 27.
    assert count_calls(graph, "Image.and") == 27


def test_band_name_argument_wins_over_the_table_band(ee_offline):
    """engine/indicator.py renames the same table to indicator_15_3_1 (§7)."""
    a = ee.Image(7)
    table = TruthTable(rules=(Rule(inputs=(("a", 1),), value=1),), band="tabled")
    built = apply_truth_table([a], table, "overridden")
    expected = ee.Image(0).where(a.eq(1), 1).rename("overridden")
    assert built.serialize() == expected.serialize()


def test_rule_order_is_the_emitted_order(ee_offline):
    """Swapping two rules must change the encoded graph."""
    a = ee.Image(7)
    first = TruthTable(
        rules=(
            Rule(inputs=(("a", 1),), value=1),
            Rule(inputs=(("a", 2),), value=2),
        ),
        band="demo",
    )
    swapped = TruthTable(rules=tuple(reversed(first.rules)), band="demo")
    assert (
        apply_truth_table([a], first, "demo").serialize()
        != apply_truth_table([a], swapped, "demo").serialize()
    )


def test_arity_mismatch_raises(ee_offline):
    a = ee.Image(7)
    table = TruthTable(rules=(Rule(inputs=(("a", 1), ("b", 1)), value=1),), band="demo")
    with pytest.raises(ValueError, match="expects 2 images, got 1"):
        apply_truth_table([a], table, "demo")


def test_empty_table_raises(ee_offline):
    with pytest.raises(ValueError, match="no rules"):
        apply_truth_table([ee.Image(7)], TruthTable(rules=(), band="demo"), "demo")


def test_inconsistent_operand_order_raises(ee_offline):
    a = ee.Image(7)
    b = ee.Image(8)
    table = TruthTable(
        rules=(
            Rule(inputs=(("a", 1), ("b", 1)), value=1),
            Rule(inputs=(("b", 1), ("a", 1)), value=2),
        ),
        band="demo",
    )
    with pytest.raises(ValueError, match="operand order"):
        apply_truth_table([a, b], table, "demo")
