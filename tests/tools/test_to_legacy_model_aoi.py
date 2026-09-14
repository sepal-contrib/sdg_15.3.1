"""``_feature_collection`` must build the AOI collection exactly as
``ExecutionContext.from_aoi_spec`` does -- its own docstring says so
(``tools/to_legacy_model.py``), and ``sdg1531/engine/context.py``'s module
docstring is why: the AOI is ``HELD_CONSTANT["aoi_leaf"]``, an input neither side
of the parity harness compares, so nothing except this check would notice the
two functions drift apart.

Checked by AST, not by running both: running the domain side needs ``ee``, and
the offline parity suite never imports this module at all (it runs only during
stage-A recording, against the legacy tree, with network) -- see task 16's
review, Minor 1. A hand run confirmed a wrong collection in either branch
leaves ``pytest -m "not network"`` and ``-m parity`` both green; this is what
closes that gap.
"""

from __future__ import annotations

import ast
from pathlib import Path

from conftest import REPO_ROOT

CONTEXT_SOURCE = REPO_ROOT / "sdg1531" / "engine" / "context.py"
ADAPTER_SOURCE = REPO_ROOT / "tools" / "to_legacy_model.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function_body(tree: ast.Module, name: str) -> list[ast.stmt]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node.body
    raise AssertionError(f"no {name!r} found in the parsed tree")


def _leaf_statements(stmts: list[ast.stmt]) -> list[ast.stmt]:
    """Flatten one statement list through ``Try``/``With``/``For``/``While``/
    ``If.body``, so a branch's collection expression is found however deep it
    is nested -- including the admin arm's ``try`` around the ``pygaul`` call
    -- without ever descending into a nested ``If``'s ``orelse``, which would
    pull a later elif branch into this one."""
    out: list[ast.stmt] = []
    for stmt in stmts:
        out.append(stmt)
        if isinstance(stmt, ast.Try):
            out += _leaf_statements(stmt.body)
            for handler in stmt.handlers:
                out += _leaf_statements(handler.body)
            out += _leaf_statements(stmt.orelse)
            out += _leaf_statements(stmt.finalbody)
        elif isinstance(stmt, (ast.If, ast.With, ast.For, ast.While)):
            out += _leaf_statements(stmt.body)
    return out


def _aoi_arm_dispatch(func_body: list[ast.stmt]) -> dict[str, str]:
    """Map each AOI arm checked via ``isinstance(aoi, X)`` to the source text of
    the collection expression its branch builds -- either a ``collection = ...``
    assignment (``from_aoi_spec``) or a bare ``return ...`` (``_feature_collection``).

    Handles both dispatch shapes the same way: an if/elif/else chain (nested
    through ``orelse``) and a sequence of standalone early-return ``if``s
    (siblings in the body) -- recursing into ``orelse`` covers the first, and
    the outer loop over every statement in ``func_body`` covers the second.
    """
    dispatch: dict[str, str] = {}

    def _collect(stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            if (
                isinstance(stmt, ast.If)
                and isinstance(stmt.test, ast.Call)
                and isinstance(stmt.test.func, ast.Name)
                and stmt.test.func.id == "isinstance"
                and len(stmt.test.args) == 2
                and isinstance(stmt.test.args[1], ast.Name)
            ):
                arm = stmt.test.args[1].id
                for leaf in _leaf_statements(stmt.body):
                    if isinstance(leaf, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "collection" for t in leaf.targets
                    ):
                        dispatch[arm] = ast.unparse(leaf.value)
                        break
                    if isinstance(leaf, ast.Return) and leaf.value is not None:
                        dispatch[arm] = ast.unparse(leaf.value)
                        break
                _collect(stmt.orelse)

    _collect(func_body)
    return dispatch


def test_the_scan_found_both_dispatch_functions() -> None:
    """An empty dispatch on either side would make the comparison below vacuous."""
    domain = _aoi_arm_dispatch(_function_body(_parse(CONTEXT_SOURCE), "from_aoi_spec"))
    legacy = _aoi_arm_dispatch(_function_body(_parse(ADAPTER_SOURCE), "_feature_collection"))

    assert len(domain) >= 3, domain
    assert len(legacy) >= 3, legacy


def test_feature_collection_spells_every_arm_exactly_as_from_aoi_spec_does() -> None:
    domain = _aoi_arm_dispatch(_function_body(_parse(CONTEXT_SOURCE), "from_aoi_spec"))
    legacy = _aoi_arm_dispatch(_function_body(_parse(ADAPTER_SOURCE), "_feature_collection"))

    assert set(legacy) == set(domain), (legacy, domain)
    mismatched = {arm: (domain[arm], legacy[arm]) for arm in domain if domain[arm] != legacy[arm]}
    assert mismatched == {}, mismatched
