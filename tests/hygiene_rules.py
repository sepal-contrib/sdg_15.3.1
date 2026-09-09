"""The AST rules behind Tier 0 guard 4. Pure; no imports from sdg1531."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from conftest import REPO_ROOT

# the packages the walk covers, by name (spec §12 Tier 0: "over both sdg1531/ and
# the app package"). Missing roots are skipped so this holds before the app lands.
ROOTS = ("sdg1531", "app")

BANNED_PARAMS = frozenset({"output", "model", "aoi_model", "alert"})
BANNED_CALL_ATTRS = frozenset({"getInfo", "getDownloadURL"})
BANNED_CALL_NAMES = frozenset({"print", "urlopen"})
FS_CALL_NAMES = frozenset({"open"})
FS_CALL_ATTRS = frozenset(
    {
        "mkdir",
        "makedirs",
        "write_text",
        "write_bytes",
        "read_text",
        "read_bytes",
        "to_csv",
        "to_file",
        "rmtree",
        "unlink",
        "expanduser",
        "home",
        "cwd",
    }
)
# zonal_shapefile_zip must round-trip a GeoDataFrame through a shapefile driver;
# it does that inside a TemporaryDirectory and returns bytes (spec D12).
FS_EXEMPT_FILES = frozenset({"sdg1531/export.py"})
ENGINE_PREFIX = "sdg1531/engine/"
RESOLVED_NAMES = frozenset({"resolved", "r"})
# Global Constraints, "No module-level mutable state": a module-level dict/list/set
# is writable by every importer, which is how widget/transition_matrix.py:46 leaks
# one user's matrix into every other Solara session. __all__ is exempt: it is a
# module attribute the interpreter reads, and guard `missing-dunder-all` owns it.
MUTABLE_LITERAL_NODES = (
    ast.Dict,
    ast.List,
    ast.Set,
    ast.DictComp,
    ast.ListComp,
    ast.SetComp,
)
MUTABLE_BUILTINS = frozenset({"dict", "list", "set"})


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.detail}"


def _is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    a = node.args
    names = [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    if a.vararg:
        names.append(a.vararg.arg)
    if a.kwarg:
        names.append(a.kwarg.arg)
    return names


def _is_mutable_container(value: ast.expr) -> bool:
    """True when ``value`` evaluates to a fresh mutable dict, list or set.

    Only the outermost expression is judged. ``MappingProxyType({...})`` and
    ``frozenset({...})`` therefore pass: the literal they wrap is unreachable
    once the call returns. Tuples, constants and every other call fall through.
    """
    if isinstance(value, MUTABLE_LITERAL_NODES):
        return True
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Name):
            return func.id in MUTABLE_BUILTINS
        if isinstance(func, ast.Attribute):
            return func.attr in MUTABLE_BUILTINS
    return False


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [t.id for t in targets if isinstance(t, ast.Name)]


def check_source(rel_path: str, source: str) -> list[Violation]:
    """Return every hygiene violation in ``source``. ``rel_path`` is POSIX, repo-relative."""
    tree = ast.parse(source, filename=rel_path)
    out: list[Violation] = []

    def add(node: ast.AST, rule: str, detail: str) -> None:
        out.append(Violation(rel_path, getattr(node, "lineno", 0), rule, detail))

    # --- module level -----------------------------------------------------
    body = [n for n in tree.body if not _is_docstring(n)]
    has_all = any(
        isinstance(n, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(t, ast.Name) and t.id == "__all__"
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
        )
        for n in tree.body
    )
    if body and not has_all:
        add(tree.body[0] if tree.body else tree, "missing-dunder-all", "module defines no __all__")

    for node in body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            add(node, "module-level-call", "import-time call; the package must be side-effect free")

        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            names = _assigned_names(node)
            if "__all__" not in names and _is_mutable_container(node.value):
                target = names[0] if names else "<target>"
                add(
                    node,
                    "module-level-mutable",
                    f"{target} is a mutable container; wrap a mapping in "
                    "MappingProxyType(...) and a collection in a tuple or frozenset",
                )

    # --- whole tree -------------------------------------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            add(node, "star-import", f"from {node.module} import *")

        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Name) and fn.id == "globals":
                add(node, "globals-subscript", "reflective dispatch; use an explicit table")

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            for name in _param_names(node):
                if name in BANNED_PARAMS:
                    add(node, "banned-param", f"public {node.name}() takes '{name}'")

        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else None
            attr = fn.attr if isinstance(fn, ast.Attribute) else None

            if name in BANNED_CALL_NAMES or attr in BANNED_CALL_ATTRS:
                add(node, "banned-call", f"{name or attr}() is forbidden in the domain")

            if rel_path not in FS_EXEMPT_FILES and (name in FS_CALL_NAMES or attr in FS_CALL_ATTRS):
                add(node, "filesystem", f"{name or attr}() touches the filesystem")

            if (name == "replace" or attr == "replace") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Name) and first.id in RESOLVED_NAMES:
                    add(node, "resolved-replace", "a ResolvedSpec is obtained only from resolve()")

        if isinstance(node, ast.Name) and node.id == "apply_truth_table" and not rel_path.startswith(ENGINE_PREFIX):
            add(node, "truth-table-leak", "apply_truth_table is engine-private")

    return out


def iter_domain_sources() -> list[tuple[str, str]]:
    """Every ``.py`` under the covered roots, as ``(repo-relative posix path, source)``."""
    found: list[tuple[str, str]] = []
    for root in ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            found.append((rel, path.read_text(encoding="utf-8")))
    return found
