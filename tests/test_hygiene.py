"""Tier 0 guard 4 — the AST hygiene walk (spec §7 defect register, §4 UI boundary).

Runs over the domain package and, once it exists, the app package. Every rule is
also exercised against a planted violation, so the guard cannot silently rot into
a no-op the day someone reorders the AST.
"""

from __future__ import annotations

import pytest
from hygiene_rules import check_source, iter_domain_sources


def test_the_walk_actually_found_the_domain() -> None:
    """An empty parametrize passes vacuously, so pin that the walk found sources.

    Without this, a rename of ``sdg1531/`` (or a bug in ``ROOTS``) would turn
    guard 4 into a silent no-op instead of a failure.
    """
    paths = [rel for rel, _ in iter_domain_sources()]
    assert "sdg1531/__init__.py" in paths, paths
    assert len(paths) == len(set(paths)), paths


_DOMAIN_SOURCES = iter_domain_sources()
# guards this parametrize specifically: an empty list would make the test below pass
# vacuously even if test_the_walk_actually_found_the_domain were ever deleted or skipped.
assert _DOMAIN_SOURCES, "iter_domain_sources() found nothing; guard 4 would run over zero files"


@pytest.mark.parametrize("rel_path,source", _DOMAIN_SOURCES, ids=lambda v: v if isinstance(v, str) and v.endswith(".py") else "")
def test_domain_source_is_clean(rel_path: str, source: str) -> None:
    violations = check_source(rel_path, source)
    assert violations == [], "\n".join(str(v) for v in violations)


def _rules(source: str, rel_path: str = "sdg1531/probe.py") -> set[str]:
    return {v.rule for v in check_source(rel_path, source)}


def test_star_import_is_rejected() -> None:
    assert "star-import" in _rules("__all__ = []\nfrom os.path import *\n")


def test_missing_dunder_all_is_rejected() -> None:
    assert "missing-dunder-all" in _rules("def f() -> int:\n    return 1\n")


def test_docstring_only_module_needs_no_dunder_all() -> None:
    assert _rules('"""nothing here yet."""\n') == set()


def test_globals_subscript_is_rejected() -> None:
    src = '__all__ = ["f"]\ndef f(name):\n    return globals()[name]\n'
    assert "globals-subscript" in _rules(src)


@pytest.mark.parametrize("param", ["output", "model", "aoi_model", "alert"])
def test_widget_bag_parameters_are_rejected(param: str) -> None:
    src = f'__all__ = ["f"]\ndef f(a, {param}=None):\n    return a\n'
    assert "banned-param" in _rules(src)


def test_private_helper_may_keep_a_banned_parameter() -> None:
    # underscore-private helpers are the escape hatch; the rule is about the API
    src = '__all__ = []\ndef _f(a, model=None):\n    return a\n'
    assert "banned-param" not in _rules(src)


@pytest.mark.parametrize(
    "expr", ["x.getInfo()", "fc.getDownloadURL(filetype='geojson')", "urlopen(url)", "print('hi')"]
)
def test_blocking_and_noisy_calls_are_rejected(expr: str) -> None:
    src = f'__all__ = ["f"]\ndef f(x, fc, url, urlopen):\n    return {expr}\n'
    assert "banned-call" in _rules(src)


def test_filesystem_access_is_rejected() -> None:
    src = '__all__ = ["f"]\nfrom pathlib import Path\ndef f():\n    return Path.home()\n'
    assert "filesystem" in _rules(src)


def test_export_module_may_write_a_temp_shapefile() -> None:
    src = '__all__ = ["f"]\ndef f(gdf, path):\n    gdf.to_file(path)\n'
    assert "filesystem" not in _rules(src, rel_path="sdg1531/export.py")
    assert "filesystem" in _rules(src, rel_path="sdg1531/stats/decode.py")


def test_module_level_call_is_rejected() -> None:
    src = '__all__ = []\nimport os\nos.makedirs("/tmp/x")\n'
    assert "module-level-call" in _rules(src)


@pytest.mark.parametrize(
    "value",
    [
        '{"a": 1}',
        "[1, 2]",
        "{1, 2}",
        '{k: 1 for k in "ab"}',
        "[n for n in range(3)]",
        'dict(a=1)',
        "list(range(3))",
    ],
)
def test_module_level_mutable_container_is_rejected(value: str) -> None:
    # widget/transition_matrix.py:46 index-assigns into a module-level constant,
    # which under Solara leaks one user's matrix into every other session.
    src = f'__all__ = ["T"]\nT = {value}\n'
    assert "module-level-mutable" in _rules(src)


@pytest.mark.parametrize(
    "value",
    [
        'MappingProxyType({"a": 1})',
        "frozenset({1, 2})",
        "tuple(range(3))",
        "(1, 2, 3)",
        "-32768",
        're.compile(r"x")',
    ],
)
def test_immutable_module_level_constant_is_accepted(value: str) -> None:
    src = f'__all__ = ["T"]\nimport re\nfrom types import MappingProxyType\nT = {value}\n'
    assert "module-level-mutable" not in _rules(src)


@pytest.mark.parametrize("dunder_all", ['("f",)', '["f"]'])
def test_dunder_all_is_never_a_mutable_state_violation(dunder_all: str) -> None:
    src = f"__all__ = {dunder_all}\ndef f() -> int:\n    return 1\n"
    assert "module-level-mutable" not in _rules(src)


def test_apply_truth_table_outside_engine_is_rejected() -> None:
    src = '__all__ = ["f"]\ndef f(imgs, table):\n    return apply_truth_table(imgs, table, "b")\n'
    assert "truth-table-leak" in _rules(src, rel_path="sdg1531/stats/requests.py")
    assert "truth-table-leak" not in _rules(src, rel_path="sdg1531/engine/indicator.py")


def test_replacing_a_resolved_spec_is_rejected() -> None:
    src = (
        '__all__ = ["f"]\n'
        "from dataclasses import replace\n"
        "def f(resolved):\n"
        "    return replace(resolved, analysis_scale=30)\n"
    )
    assert "resolved-replace" in _rules(src)
