"""The AST rules behind Tier 0 guard 4. Pure; no imports from sdg1531."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from conftest import REPO_ROOT

# the packages the walk covers, by name (spec §12 Tier 0: "over both sdg1531/ and
# the app package"). Missing roots are skipped so this holds before the app lands.
ROOTS = ("sdg1531", "app")

BANNED_PARAMS = frozenset({"output", "model", "aoi_model", "alert"})
BANNED_CALL_ATTRS = frozenset({"getInfo", "getDownloadURL", "urlopen"})
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
        "open",
    }
)
# zonal_shapefile_zip must round-trip a GeoDataFrame through a shapefile driver and
# read the zipped result back as bytes (spec D12) — that write-then-read pair is the
# only filesystem access sdg1531/export.py is allowed; everything else there (mkdir,
# rmtree, home, ...) is still flagged like anywhere else in the domain.
FS_EXEMPT_FILES = frozenset({"sdg1531/export.py"})
FS_EXEMPT_CALLS = frozenset({"to_file", "read_bytes"})
ENGINE_PREFIX = "sdg1531/engine/"
ENGINE_MODULE = "sdg1531/engine.py"
# "resolved"/"r" missed the common instance-attribute spelling (self.resolved) and the
# unabbreviated parameter name; widened, not made a substring match, so it still only
# catches a ResolvedSpec, not any object with "resolved" somewhere in its name.
RESOLVED_NAMES = frozenset({"resolved", "r", "resolved_spec"})
# Global Constraints, "No module-level mutable state": a module-level dict/list/set
# is writable by every importer, which is how widget/transition_matrix.py:46 leaks
# one user's matrix into every other Solara session. The same is true of a top-level
# class's own attributes (shared across every instance and importer) — see the
# module-level check below, which also walks ClassDef bodies. __all__ and __slots__
# are exempt: both are attribute lists the interpreter itself reads.
MUTABLE_CHECK_EXEMPT_NAMES = frozenset({"__all__", "__slots__"})
MUTABLE_LITERAL_NODES = (
    ast.Dict,
    ast.List,
    ast.Set,
    ast.DictComp,
    ast.ListComp,
    ast.SetComp,
)
# dict/list/set caught the literal-producing builtins but missed the stdlib factories
# (defaultdict(list), OrderedDict(), Counter(), deque(), bytearray()) and sorted(),
# which all hand back the same kind of fresh, writable container.
MUTABLE_BUILTINS = frozenset(
    {"dict", "list", "set", "defaultdict", "OrderedDict", "Counter", "deque", "bytearray", "sorted"}
)


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.detail}"


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    a = node.args
    names = [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    if a.vararg:
        names.append(a.vararg.arg)
    if a.kwarg:
        names.append(a.kwarg.arg)
    return names


def _is_mutable_container(value: ast.expr) -> bool:
    """True when ``value`` evaluates to a fresh mutable container.

    Only the outermost expression is judged. ``MappingProxyType({...})`` and
    ``frozenset({...})`` therefore pass: the literal they wrap is unreachable
    once the call returns. A ``BinOp`` (``{"a": 1} | {"b": 2}``) is judged by its
    operands, since combining two mutable containers is still a mutable container.
    Tuples, constants and every other call fall through.
    """
    if isinstance(value, MUTABLE_LITERAL_NODES):
        return True
    if isinstance(value, ast.BinOp):
        return _is_mutable_container(value.left) or _is_mutable_container(value.right)
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Name):
            return func.id in MUTABLE_BUILTINS
        if isinstance(func, ast.Attribute):
            return func.attr in MUTABLE_BUILTINS
    return False


def _looks_like_a_resolved_spec(node: ast.expr) -> bool:
    """True for a bare name or attribute access whose name suggests a ResolvedSpec.

    Attribute access (``self.resolved``) matters because a ResolvedSpec is normally
    threaded through as an instance attribute, not a bare local.
    """
    if isinstance(node, ast.Name):
        return node.id in RESOLVED_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in RESOLVED_NAMES
    return False


def _is_engine_source(rel_path: str) -> bool:
    return rel_path == ENGINE_MODULE or rel_path.startswith(ENGINE_PREFIX)


def _binding_targets(node: ast.Assign | ast.AnnAssign) -> list[tuple[str, ast.expr]]:
    """Pairs of ``(bound name, value expression)`` for a module- or class-level assignment.

    Handles a plain ``NAME = value`` and element-wise tuple/list unpacking such as
    ``A, B = {}, []``. An unpacking whose value isn't itself a literal tuple/list
    (``A, B = get_pair()``) is left alone — the AST can't tell what it yields.
    """
    if isinstance(node, ast.AnnAssign):
        if node.value is None or not isinstance(node.target, ast.Name):
            return []
        return [(node.target.id, node.value)]

    value = node.value
    pairs: list[tuple[str, ast.expr]] = []
    for target in node.targets:
        if isinstance(target, ast.Name):
            pairs.append((target.id, value))
        elif (
            isinstance(target, (ast.Tuple, ast.List))
            and isinstance(value, (ast.Tuple, ast.List))
            and len(target.elts) == len(value.elts)
        ):
            for t_elt, v_elt in zip(target.elts, value.elts, strict=True):
                if isinstance(t_elt, ast.Name):
                    pairs.append((t_elt.id, v_elt))
    return pairs


def check_source(rel_path: str, source: str) -> list[Violation]:
    """Return every hygiene violation in ``source``. ``rel_path`` is POSIX, repo-relative."""
    tree = ast.parse(source, filename=rel_path)
    out: list[Violation] = []

    def add(node: ast.AST, rule: str, detail: str) -> None:
        out.append(Violation(rel_path, getattr(node, "lineno", 0), rule, detail))

    def flag_if_mutable(
        stmt: ast.stmt, name: str, value: ast.expr, *, owner: str | None = None
    ) -> None:
        if name in MUTABLE_CHECK_EXEMPT_NAMES or not _is_mutable_container(value):
            return
        label = f"{owner}.{name}" if owner else name
        add(
            stmt,
            "module-level-mutable",
            f"{label} is a mutable container; wrap a mapping in "
            "MappingProxyType(...) and a collection in a tuple or frozenset",
        )

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

        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target_name, value in _binding_targets(node):
                flag_if_mutable(node, target_name, value)

        if isinstance(node, ast.ClassDef):
            for class_stmt in node.body:
                if not isinstance(class_stmt, (ast.Assign, ast.AnnAssign)):
                    continue
                for target_name, value in _binding_targets(class_stmt):
                    flag_if_mutable(class_stmt, target_name, value, owner=node.name)

    # --- whole tree -------------------------------------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            add(node, "star-import", f"from {node.module} import *")

        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Name) and fn.id == "globals":
                add(node, "globals-subscript", "reflective dispatch; use an explicit table")

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(
            "_"
        ):
            for name in _param_names(node):
                if name in BANNED_PARAMS:
                    add(node, "banned-param", f"public {node.name}() takes '{name}'")

        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else None
            attr = fn.attr if isinstance(fn, ast.Attribute) else None

            if name in BANNED_CALL_NAMES or attr in BANNED_CALL_ATTRS:
                add(node, "banned-call", f"{name or attr}() is forbidden in the domain")

            exempt = rel_path in FS_EXEMPT_FILES and attr in FS_EXEMPT_CALLS
            if not exempt and (name in FS_CALL_NAMES or attr in FS_CALL_ATTRS):
                add(node, "filesystem", f"{name or attr}() touches the filesystem")

            if (
                (name == "replace" or attr == "replace")
                and node.args
                and _looks_like_a_resolved_spec(node.args[0])
            ):
                add(node, "resolved-replace", "a ResolvedSpec is obtained only from resolve()")

        if (
            isinstance(node, ast.Name)
            and node.id == "apply_truth_table"
            and not _is_engine_source(rel_path)
        ):
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
