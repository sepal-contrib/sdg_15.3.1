"""``tools/to_legacy_model.py`` writes real traits, and all of the ones that matter.

Every golden graph is only as correct as this adapter. Nothing type-checks it: the
legacy tree is untyped, so ``pyproject.toml`` sets ``follow_imports = "skip"`` for
``component.*``, which makes ``IndicatorModel`` an ``Any``. Under an ``Any``,
``model.thresholdd = 0.0`` type-checks clean -- and traitlets does not object
either, since ``HasTraits`` lets an unknown attribute name become a plain instance
attribute. The typo would produce a golden recorded from a run with the threshold
left at its default, and the port would then be validated against it, green.

Until now the only thing standing between that and the goldens was two reviewers
reading the file trait by trait. This checks it instead, in three directions, all
of them derived by AST scan:

1. every trait the adapter WRITES is declared on ``IndicatorModel``;
2. every attribute it READS is declared there too;
3. every trait the legacy compute path reads is one the adapter writes -- except
   the seven ``run_15_3_1.py`` writes itself, which are outputs, not inputs. That
   exemption is derived as well, so it cannot grow quietly.

Nothing here imports ``component``. Importing it runs
``component/parameter/directory.py:6-10``, which mkdirs ``~/module_results``.
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path

from conftest import REPO_ROOT

MODEL_SOURCE = REPO_ROOT / "component" / "model" / "indicator_model.py"
ADAPTER_SOURCE = REPO_ROOT / "tools" / "to_legacy_model.py"
COMPUTE_PATH = REPO_ROOT / "component" / "scripts"

# The adapter's local name for the IndicatorModel it populates.
MODEL_VARIABLE = "model"


def _parse(path: Path) -> ast.Module:
    """Parse without echoing the legacy tree's SyntaxWarnings into the test output."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _model_class() -> ast.ClassDef:
    for node in _parse(MODEL_SOURCE).body:
        if isinstance(node, ast.ClassDef) and node.name == "IndicatorModel":
            return node
    raise AssertionError(f"no IndicatorModel in {MODEL_SOURCE}")


def _declared() -> tuple[frozenset[str], frozenset[str]]:
    """``(traits, methods)`` -- the class-body assignments and the defs on them."""
    traits: set[str] = set()
    methods: set[str] = set()
    for node in _model_class().body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            traits |= {t.id for t in targets if isinstance(t, ast.Name)}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.add(node.name)
    return frozenset(traits), frozenset(methods)


def _attributes_of(tree: ast.AST, variable: str, *, store: bool) -> frozenset[str]:
    """Every ``<variable>.<attr>`` in ``tree``, read or written."""
    wanted = ast.Store if store else ast.Load
    return frozenset(
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == variable
        and isinstance(node.ctx, wanted)
    )


def _compute_path_attributes(*, store: bool) -> frozenset[str]:
    found: set[str] = set()
    for path in sorted(COMPUTE_PATH.glob("*.py")):
        found |= _attributes_of(_parse(path), MODEL_VARIABLE, store=store)
    return frozenset(found)


def _property_self_reads() -> frozenset[str]:
    """``self.<attr>`` inside IndicatorModel's own properties.

    ``p_trend_start`` and its fifteen siblings read the input traits the compute
    path never touches by name, so a scan of ``component/scripts/`` alone would
    miss ``trend_start`` and let the adapter stop setting it unnoticed.
    """
    found: set[str] = set()
    for node in _model_class().body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found |= _attributes_of(node, "self", store=False)
    return frozenset(found)


def test_the_scans_found_the_legacy_model_and_the_adapter() -> None:
    """Three of the assertions below are subset checks, which an empty left side
    satisfies. Nothing here may run over zero names."""
    traits, methods = _declared()

    assert len(traits) > 20, sorted(traits)
    assert "scale" in methods, sorted(methods)
    assert len(_attributes_of(_parse(ADAPTER_SOURCE), MODEL_VARIABLE, store=True)) > 20
    assert len(_compute_path_attributes(store=False)) > 20


def test_every_trait_the_adapter_writes_is_declared_on_the_legacy_model() -> None:
    traits, methods = _declared()
    written = _attributes_of(_parse(ADAPTER_SOURCE), MODEL_VARIABLE, store=True)

    invented = sorted(written - traits - methods)
    assert invented == [], (
        f"the adapter sets attributes IndicatorModel does not declare: {invented}. "
        "traitlets accepts them silently, and every golden recorded through this "
        "adapter would carry the default instead."
    )


def test_every_attribute_the_adapter_reads_is_declared_on_the_legacy_model() -> None:
    traits, methods = _declared()
    read = _attributes_of(_parse(ADAPTER_SOURCE), MODEL_VARIABLE, store=False)

    unknown = sorted(read - traits - methods)
    assert unknown == [], f"the adapter reads attributes IndicatorModel does not have: {unknown}"


def test_every_input_trait_the_legacy_compute_path_reads_is_populated() -> None:
    """The other direction: a trait the science reads that the adapter never sets
    is a trait every golden was recorded with at its declared default.

    The exemption is derived rather than listed -- the traits ``run_15_3_1.py``
    ASSIGNS are its outputs (the seven layer images), and an input the adapter must
    supply is exactly one the compute path reads and never writes.
    """
    traits, _ = _declared()
    written_by_the_adapter = _attributes_of(_parse(ADAPTER_SOURCE), MODEL_VARIABLE, store=True)
    outputs = _compute_path_attributes(store=True) & traits
    inputs = ((_compute_path_attributes(store=False) | _property_self_reads()) & traits) - outputs

    assert outputs, "the compute path assigns no trait at all; the exemption is vacuous"
    unpopulated = sorted(inputs - written_by_the_adapter)
    assert unpopulated == [], (
        f"traits the legacy science reads but the adapter never sets: {unpopulated}"
    )


def test_the_adapter_sets_nothing_the_legacy_compute_path_ignores() -> None:
    """A write nothing reads is either a trait that moved or a mapping written
    against the wrong name; either way the reviewed line-for-line reading of
    ``indicator_model.py`` that this file replaces would no longer hold."""
    traits, _ = _declared()
    written = _attributes_of(_parse(ADAPTER_SOURCE), MODEL_VARIABLE, store=True)
    read = (_compute_path_attributes(store=False) | _property_self_reads()) & traits

    dead = sorted(written - read)
    assert dead == [], f"the adapter sets traits nothing on the compute path reads: {dead}"
