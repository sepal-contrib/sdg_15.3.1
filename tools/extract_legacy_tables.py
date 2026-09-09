"""AST-lift the three legacy `.where()` chains into a committed fixture.

Spec §12 Tier 2. The three chains are the port's biggest transcription risk:
66 hand-written rules whose values a reviewer cannot check by eye. This tool
reads them out of the legacy source with `ast`, so `sdg1531/truth_table.py`
can be diffed against the original mechanically.

Encoding: an operand `img.eq(k)` for k >= 1 becomes the pair (name, k); `img.lt(1)`
— used only by run_15_3_1.py:406-408 — becomes (name, 0). `img.eq(0)` is refused
rather than folded onto that same (name, 0): the two predicates read identically
here, but the emitter this feeds always spells class 0 as `.lt(1)`, never
`.eq(0)`, so accepting the latter would let a mistranscribed chain through
looking correct. A shadowed function name, or a function with more than one
`.where()`-chain assignment, is refused the same way: Python's own name binding
and control flow pick exactly one of those at runtime, and this tool refuses to
guess which one that would be. Nothing else is accepted.

The output is committed to `tests/fixtures/legacy_tables.json` so this evidence of
correctness survives `component/` eventually being deleted. Its faithfulness to
source is not assumed: `tests/tools/test_extract_legacy_tables.py`'s
`test_fixture_is_regenerated_from_source` re-runs this tool against the live
legacy files on every test run and fails the moment the committed JSON and the
source disagree — so re-run this script and re-commit the fixture whenever one
of the three legacy chains changes.

Run:  python tools/extract_legacy_tables.py --out tests/fixtures/legacy_tables.json
"""

from __future__ import annotations

import argparse
import ast
import json
import warnings
from pathlib import Path

TARGETS = (
    # (table name, legacy file, enclosing function)
    ("productivity_final", "component/scripts/productivity.py", "productivity_final"),
    (
        "productivity_final_GPG1",
        "component/scripts/productivity.py",
        "productivity_final_GPG1",
    ),
    ("indicator_15_3_1", "component/scripts/run_15_3_1.py", "indicator_15_3_1"),
)


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if not matches:
        raise ValueError(f"no function named {name}")
    if len(matches) > 1:
        # Python binds a shadowed name to the *last* def, not the first; picking
        # either without checking would silently extract the wrong function.
        raise ValueError(
            f"{len(matches)} functions named {name} in this module — ambiguous "
            "which one Python would actually bind, refusing to guess"
        )
    return matches[0]


def _find_chain(func: ast.FunctionDef) -> ast.Assign:
    matches = []
    for node in func.body:
        if not isinstance(node, ast.Assign):
            continue
        cur = node.value
        while isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute):
            if cur.func.attr == "where":
                matches.append(node)
                break
            cur = cur.func.value
    if not matches:
        raise ValueError(f"no .where() chain in {func.name}")
    if len(matches) > 1:
        raise ValueError(
            f"{len(matches)} .where() chains assigned in {func.name} — ambiguous "
            "which one is the function's actual result, refusing to guess"
        )
    return matches[0]


def _operand(node: ast.AST) -> tuple[str, int]:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        raise ValueError(f"unsupported comparison: {ast.dump(node)}")
    attr = node.func.attr
    target = node.func.value
    if not isinstance(target, ast.Name):
        raise ValueError(f"unsupported comparison target: {ast.dump(target)}")
    if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
        raise ValueError(f"unsupported comparison argument in .{attr}()")
    argument = node.args[0].value
    if attr == "eq" and argument == 0:
        # class 0 is only ever spelled `.lt(1)` in the legacy chains
        # (run_15_3_1.py:406-408); an `.eq(0)` would be silently
        # indistinguishable from that once encoded as (name, 0).
        raise ValueError(f"ambiguous .eq(0) in .{attr}() — class 0 must be .lt(1)")
    if attr == "eq":
        cls = int(argument)
    elif attr == "lt" and argument == 1:
        # run_15_3_1.py:406-408 — `.lt(1)` on a uint8 band means "is 0".
        cls = 0
    else:
        raise ValueError(f"unsupported comparison .{attr}({argument!r})")
    name = target.id
    if name.endswith("_class"):
        name = name[: -len("_class")]
    return name, cls


def _unwind_and(node: ast.AST) -> list[ast.AST]:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "And"
    ):
        if len(node.args) != 1:
            raise ValueError("unsupported .And() arity")
        return [*_unwind_and(node.func.value), node.args[0]]
    return [node]


def extract_chain(source: str, function_name: str) -> dict:
    """Extract one `.where()` chain from `source` by function name."""
    with warnings.catch_warnings():
        # productivity.py:186 has an unescaped LaTeX docstring (`$$\mu = ...$$`),
        # a pre-existing legacy defect this tool must not touch or paper over
        # anywhere else; suppressed only for this one parse.
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(source)
    func = _find_function(tree, function_name)
    assign = _find_chain(func)

    band = None
    wheres: list[tuple[ast.AST, ast.AST]] = []
    cur = assign.value
    while isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute):
        attr = cur.func.attr
        if attr == "Image":
            break
        if attr == "where":
            if len(cur.args) != 2:
                raise ValueError("unsupported .where() arity")
            wheres.append((cur.args[0], cur.args[1]))
        elif attr == "rename":
            if band is not None:
                raise ValueError("two .rename() calls in one chain")
            if len(cur.args) != 1 or not isinstance(cur.args[0], ast.Constant):
                raise ValueError("unsupported .rename() argument")
            band = cur.args[0].value
        else:
            raise ValueError(f"unexpected call .{attr}() in chain")
        cur = cur.func.value

    if not (
        isinstance(cur, ast.Call)
        and isinstance(cur.func, ast.Attribute)
        and cur.func.attr == "Image"
        and isinstance(cur.func.value, ast.Name)
        and cur.func.value.id == "ee"
        and len(cur.args) == 1
        and isinstance(cur.args[0], ast.Constant)
        and cur.args[0].value == 0
    ):
        raise ValueError("chain does not start at ee.Image(0)")

    wheres.reverse()

    inputs: list[str] | None = None
    rules: list[list] = []
    for predicate, value in wheres:
        if not isinstance(value, ast.Constant):
            raise ValueError("non-literal .where() value")
        operands = [_operand(term) for term in _unwind_and(predicate)]
        names = [name for name, _ in operands]
        if inputs is None:
            inputs = names
        elif names != inputs:
            raise ValueError(f"operand order changes mid-chain: {names} != {inputs}")
        rules.append([[cls for _, cls in operands], int(value.value)])

    return {
        "inputs": inputs,
        "band": band,
        "rules": rules,
        "function_lines": [func.lineno, func.end_lineno],
        # Incidental guard, not the real one: catches a rule being inserted or
        # deleted (the chain's line span shifts), but a same-length edit to a
        # rule's value or class leaves these lines untouched. The guard that
        # actually catches a value edit is test_fixture_is_regenerated_from_source.
        "chain_lines": [assign.lineno, assign.end_lineno],
    }


def extract_all(repo_root: Path) -> dict:
    tables = []
    for name, relative, function_name in TARGETS:
        source = (repo_root / relative).read_text(encoding="utf-8")
        table = extract_chain(source, function_name)
        table["name"] = name
        table["source"] = relative
        tables.append(table)
    return {"generated_by": "tools/extract_legacy_tables.py", "tables": tables}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/legacy_tables.json"))
    args = parser.parse_args()
    payload = extract_all(args.repo_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({len(payload['tables'])} tables)")


if __name__ == "__main__":
    main()
