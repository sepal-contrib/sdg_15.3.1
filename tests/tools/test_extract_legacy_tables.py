"""The extractor lifts the three legacy `.where()` chains by AST (stage A, Tier 2).

It is the ground truth `sdg1531/truth_table.py` is checked against, so it must be
strict: any construct it does not recognise is an error, never a silent skip.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "extract_legacy_tables.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("extract_legacy_tables", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load_tool()


@pytest.fixture(scope="module")
def extracted(tool):
    return tool.extract_all(REPO_ROOT)


def _table(extracted, name):
    matches = [t for t in extracted["tables"] if t["name"] == name]
    assert len(matches) == 1, f"expected exactly one table named {name}"
    return matches[0]


def test_three_tables_are_extracted(extracted):
    assert [t["name"] for t in extracted["tables"]] == [
        "productivity_final",
        "productivity_final_GPG1",
        "indicator_15_3_1",
    ]


def test_rule_counts_are_18_18_30(extracted):
    assert len(_table(extracted, "productivity_final")["rules"]) == 18
    assert len(_table(extracted, "productivity_final_GPG1")["rules"]) == 18
    assert len(_table(extracted, "indicator_15_3_1")["rules"]) == 30


def test_operand_names_come_from_the_legacy_locals(extracted):
    assert _table(extracted, "productivity_final")["inputs"] == [
        "trajectory",
        "state",
        "performance",
    ]
    assert _table(extracted, "productivity_final_GPG1")["inputs"] == [
        "trajectory",
        "state",
        "performance",
    ]
    assert _table(extracted, "indicator_15_3_1")["inputs"] == [
        "productivity",
        "landcover",
        "soc",
    ]


def test_source_order_is_preserved(extracted):
    """The first six rules of productivity_final, verbatim from productivity.py:259-282."""
    rules = _table(extracted, "productivity_final")["rules"]
    assert rules[:6] == [
        [[1, 1, 1], 1],
        [[1, 1, 2], 1],
        [[1, 2, 1], 1],
        [[1, 2, 2], 2],
        [[1, 3, 1], 1],
        [[1, 3, 2], 1],
    ]


def test_lt_one_is_encoded_as_class_zero(extracted):
    """run_15_3_1.py:406-408 uses .lt(1), not .eq(0); it becomes class 0."""
    rules = _table(extracted, "indicator_15_3_1")["rules"]
    assert rules[-3:] == [
        [[1, 0, 0], 1],
        [[0, 1, 0], 1],
        [[0, 0, 1], 1],
    ]


def test_band_is_the_rename_argument_or_none(extracted):
    assert _table(extracted, "productivity_final")["band"] == "productivity"
    assert _table(extracted, "productivity_final_GPG1")["band"] == "productivity"
    # run_15_3_1.py:377-409 never calls .rename() — the unnamed-band defect.
    assert _table(extracted, "indicator_15_3_1")["band"] is None


def test_chain_line_numbers_are_recorded(extracted):
    """Incidental guard: catches an inserted/deleted rule, not a same-length value
    edit. `test_fixture_is_regenerated_from_source` below is the real guard against
    the fixture going stale.
    """
    assert _table(extracted, "productivity_final")["chain_lines"] == [257, 332]
    assert _table(extracted, "productivity_final_GPG1")["chain_lines"] == [342, 417]
    assert _table(extracted, "indicator_15_3_1")["chain_lines"] == [377, 409]


def test_fixture_is_regenerated_from_source(extracted):
    """The committed fixture must equal a fresh extraction, rule for rule.

    Every other test here spot-checks a handful of rules (counts, the first six,
    the last three, chain_lines); none of that would notice a single mid-chain
    rule's value being edited in place. This compares all 66 rules of all three
    tables, so `sdg1531/truth_table.py`'s parity with the committed JSON
    (asserted in tests/test_truth_table.py) is actually parity with source, not
    just with a JSON file that quietly went stale.
    """
    committed = json.loads((REPO_ROOT / "tests" / "fixtures" / "legacy_tables.json").read_text())
    assert extracted == committed


def test_eq_zero_is_rejected_not_aliased_to_lt_one(tool):
    """`.eq(0)` would encode to the same (name, 0) as `.lt(1)` — refuse it outright
    rather than let it through indistinguishable from the real class-0 predicate.
    """
    source = (
        "def f():\n    x = ee.Image(0).where(a.eq(0).And(b.eq(1)), 1).rename('x')\n    return x\n"
    )
    with pytest.raises(ValueError, match=r"ambiguous \.eq\(0\)"):
        tool.extract_chain(source, "f")


def test_multiple_where_chains_in_one_function_is_an_error(tool):
    """Two `.where()`-chain assignments in one function are ambiguous about which
    one is the actual result — refuse rather than silently pick the first.
    """
    source = (
        "def f():\n"
        "    y = ee.Image(0).where(a.eq(1), 9).rename('y')\n"
        "    x = ee.Image(0).where(a.eq(1), 1).rename('x')\n"
        "    return x\n"
    )
    with pytest.raises(ValueError, match="ambiguous which one is the function's actual result"):
        tool.extract_chain(source, "f")


def test_shadowed_function_name_is_an_error(tool):
    """Python binds a shadowed def to the *last* definition; refuse rather than
    silently extract the first, which would be the wrong one.
    """
    source = (
        "def f():\n"
        "    x = ee.Image(0).where(a.eq(1), 9).rename('first')\n"
        "    return x\n"
        "\n"
        "def f():\n"
        "    x = ee.Image(0).where(a.eq(1), 1).rename('second')\n"
        "    return x\n"
    )
    with pytest.raises(ValueError, match="ambiguous which one Python would actually bind"):
        tool.extract_chain(source, "f")


def test_unknown_predicate_is_an_error_not_a_silent_skip(tool):
    source = (
        "def f():\n    x = ee.Image(0).where(a.gt(1).And(b.eq(2)), 3).rename('x')\n    return x\n"
    )
    with pytest.raises(ValueError, match="unsupported comparison"):
        tool.extract_chain(source, "f")


def test_unknown_chain_method_is_an_error(tool):
    source = "def f():\n    x = ee.Image(0).where(a.eq(1), 3).uint8().rename('x')\n    return x\n"
    with pytest.raises(ValueError, match="unexpected call"):
        tool.extract_chain(source, "f")
