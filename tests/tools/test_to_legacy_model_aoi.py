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

The scan refuses what it cannot parse rather than skipping it. Its first
version required an ``isinstance`` second argument to be a bare name and
silently dropped anything else -- including the arm's whole branch, which
then agreed with itself on both sides of the comparison by being absent from
both. Task 16's re-review caught it: the file written to prove the two
functions stay in sync could not see them go out of sync, the fifth time
this project has found that shape of defect inside the helper meant to
prevent it. Every shape the scan does not recognise now raises, naming the
file and line, and the arm set it checks against is read from ``AoiSpec``
itself rather than a count that would happen to equal today's truth.
"""

from __future__ import annotations

import ast
import typing
from pathlib import Path

from conftest import REPO_ROOT

import sdg1531.spec

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


def _arm_names(node: ast.expr, *, source: Path, lineno: int) -> list[str]:
    """The class name(s) an ``isinstance(aoi, X)`` test's second argument
    names: a bare name (``AdminAoi``), a dotted attribute
    (``spec.AdminAoi``), or a tuple of either. Anything else is refused, not
    skipped -- a shape this cannot name must not silently vanish from the
    comparison it is part of."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.Tuple):
        return [name for elt in node.elts for name in _arm_names(elt, source=source, lineno=lineno)]
    raise AssertionError(
        f"{source}:{lineno}: isinstance()'s second argument is {ast.dump(node)!r}, a shape "
        "this scan does not know how to name as an AOI arm -- teach it, don't skip it"
    )


def _branch_expression(body: list[ast.stmt], *, source: Path, lineno: int, arm: str) -> str:
    """The source text of the ``collection = ...`` assignment or bare
    ``return ...`` inside one arm's branch. Raises, rather than leaving the
    arm out of the returned mapping, if the branch holds neither."""
    for leaf in _leaf_statements(body):
        if isinstance(leaf, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "collection" for t in leaf.targets
        ):
            return ast.unparse(leaf.value)
        if isinstance(leaf, ast.Return) and leaf.value is not None:
            return ast.unparse(leaf.value)
    raise AssertionError(
        f"{source}:{lineno}: the {arm!r} branch has no `collection = ...` assignment and no "
        "`return ...` this scan can read"
    )


def _aoi_arm_dispatch(func_body: list[ast.stmt], *, source: Path) -> dict[str, str]:
    """Map each AOI arm checked via ``isinstance(aoi, X)`` to the source text of
    the collection expression its branch builds -- either a ``collection = ...``
    assignment (``from_aoi_spec``) or a bare ``return ...`` (``_feature_collection``).

    Handles both dispatch shapes the same way: an if/elif/else chain (nested
    through ``orelse``) and a sequence of standalone early-return ``if``s
    (siblings in the body). Recursing into every ``If``'s ``orelse`` --
    whether or not that ``If`` turned out to be an isinstance dispatch --
    covers the first shape without letting one unrelated ``if`` hide the
    elif branches that follow it; the outer loop over every statement in
    ``func_body`` covers the second.
    """
    dispatch: dict[str, str] = {}

    def _collect(stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            if not isinstance(stmt, ast.If):
                continue
            test = stmt.test
            if (
                isinstance(test, ast.Call)
                and isinstance(test.func, ast.Name)
                and test.func.id == "isinstance"
                and len(test.args) == 2
            ):
                for arm in _arm_names(test.args[1], source=source, lineno=stmt.lineno):
                    dispatch[arm] = _branch_expression(
                        stmt.body, source=source, lineno=stmt.lineno, arm=arm
                    )
            _collect(stmt.orelse)

    _collect(func_body)
    return dispatch


def _aoi_spec_arm_names() -> frozenset[str]:
    """The real ``AoiSpec`` union members, read from the type alias itself --
    not a count copied from today's arm list, which would equal the truth by
    coincidence and stop noticing the day it doesn't."""
    return frozenset(cls.__name__ for cls in typing.get_args(sdg1531.spec.AoiSpec.__value__))


def test_both_dispatch_functions_cover_every_declared_aoi_arm() -> None:
    truth = _aoi_spec_arm_names()
    assert truth, "AoiSpec declares no arms at all; the derived truth is itself empty"

    domain = _aoi_arm_dispatch(
        _function_body(_parse(CONTEXT_SOURCE), "from_aoi_spec"), source=CONTEXT_SOURCE
    )
    legacy = _aoi_arm_dispatch(
        _function_body(_parse(ADAPTER_SOURCE), "_feature_collection"), source=ADAPTER_SOURCE
    )

    assert set(domain) == truth, (set(domain), truth)
    assert set(legacy) == truth, (set(legacy), truth)


def test_feature_collection_spells_every_arm_exactly_as_from_aoi_spec_does() -> None:
    domain = _aoi_arm_dispatch(
        _function_body(_parse(CONTEXT_SOURCE), "from_aoi_spec"), source=CONTEXT_SOURCE
    )
    legacy = _aoi_arm_dispatch(
        _function_body(_parse(ADAPTER_SOURCE), "_feature_collection"), source=ADAPTER_SOURCE
    )

    mismatched = {arm: (domain[arm], legacy[arm]) for arm in domain if domain[arm] != legacy[arm]}
    assert mismatched == {}, mismatched
