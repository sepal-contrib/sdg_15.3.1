"""AST-lift the three legacy `.where()` chains into a committed fixture.

Spec §12 Tier 2. The three chains are the port's biggest transcription risk:
66 hand-written rules whose values a reviewer cannot check by eye. This tool
reads them out of the legacy source with `ast`, so `sdg1531/truth_table.py`
can be diffed against the original mechanically.

Encoding: an operand `img.eq(k)` becomes the pair (name, k); `img.lt(1)` — used
only by run_15_3_1.py:406-408 — becomes (name, 0). Nothing else is accepted.

Run:  python tools/extract_legacy_tables.py --out tests/fixtures/legacy_tables.json
"""

from __future__ import annotations

import argparse
import ast
import json
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
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError(f"no function named {name}")


def _find_chain(func: ast.FunctionDef) -> ast.Assign:
    for node in func.body:
        if not isinstance(node, ast.Assign):
            continue
        cur = node.value
        while isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute):
            if cur.func.attr == "where":
                return node
            cur = cur.func.value
    raise ValueError(f"no .where() chain in {func.name}")


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
