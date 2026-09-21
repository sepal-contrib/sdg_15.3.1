"""Every ``solara.lab.use_task`` call in the app stays manual-trigger-only.

``dependencies=None`` is what makes a ``use_task`` purely click-triggered in
solara -- the runtime default is ``dependencies=[]``, which runs the task
IMMEDIATELY, on mount (see ``solara.lab.use_task``'s own docstring: "the task
is invoked immediately when dependencies are passed. To prevent this, pass
dependencies=None."). So this is not cosmetic: an omitted ``dependencies``
kwarg on any of these calls would fire real GEE work the first time a panel
mounts, with no click at all -- exactly the failure Task 20's brief warns
against when deriving ``maps`` on every spec change instead of behind a
button.

Two things make the scan itself honest, not just the property it checks:

1. It resolves ``from solara.lab import use_task as <alias>`` to the local
   name a call site actually uses, not just the literal spelling
   ``use_task``/``.use_task`` -- fix round 1's finding: a scan that only
   matches the common spelling is narrower than the property it claims to
   check, and an aliased import defeated it silently. Module-level aliasing
   (``import solara.lab as sl``) needs no separate handling: an attribute
   access can never rename its own final attribute, so ``sl.use_task(...)``
   still ends in ``.use_task`` and the attribute-name match already covers it.
2. Its vacuity floor is not a hand-typed count of "six known sites" (fix
   round 1's other finding: that number would drift the moment a real site
   moved, and a regression that dropped the scan to one or two matches would
   still clear a bare ``>= 1``). Instead it cross-checks against
   ``tests/hygiene_rules.py``'s own, independently-authored, already-exercised
   ``use-task-prefer-threaded`` rule (``test_hygiene.py::test_domain_source_is_clean``
   runs it over every real file in ``app/`` today) -- a second, differently-motivated
   AST walk that happens to also need to find every ``use_task`` call. If this
   scan ever finds fewer sites than that simpler one, it has regressed, and the
   assertion below names exactly which sites went missing.
"""

from __future__ import annotations

import ast

from hygiene_rules import iter_domain_sources


def _use_task_aliases(tree: ast.Module) -> frozenset[str]:
    """Local names this module's imports bind to ``use_task``.

    Covers ``from solara.lab import use_task`` and
    ``from solara.lab import use_task as <alias>`` (any module, not just
    ``solara.lab``, so a re-export would still be caught). Deliberately does
    NOT track plain ``import`` aliasing of the surrounding module -- see the
    module docstring for why an attribute access needs no such tracking.
    """
    return frozenset(
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == "use_task"
    )


def _is_use_task_call(call: ast.Call, aliases: frozenset[str]) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr == "use_task"
    if isinstance(func, ast.Name):
        return func.id == "use_task" or func.id in aliases
    return False


def _use_task_calls_in_source(rel_path: str, source: str) -> list[tuple[str, int, ast.Call]]:
    """Every call in ``source`` that resolves to ``use_task``, alias included."""
    tree = ast.parse(source, filename=rel_path)
    aliases = _use_task_aliases(tree)
    return [
        (rel_path, node.lineno, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_use_task_call(node, aliases)
    ]


def _naive_use_task_sites_in_source(rel_path: str, source: str) -> list[tuple[str, int]]:
    """The plain name/attr-only match ``hygiene_rules.check_source``'s own
    ``use-task-prefer-threaded`` rule uses. Reimplemented here, independently,
    rather than imported: this exists specifically to disagree with the scan
    above if the two ever diverge, which an import would make impossible."""
    tree = ast.parse(source, filename=rel_path)
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else None
        attr = func.attr if isinstance(func, ast.Attribute) else None
        if name == "use_task" or attr == "use_task":
            sites.append((rel_path, node.lineno))
    return sites


def _app_sources() -> list[tuple[str, str]]:
    """Every ``app/`` source, reusing ``hygiene_rules``'s own file walk so this
    scan and the naive cross-check below see exactly the same files as guard 4
    does -- not a second, independently-drifting glob."""
    return [(rel, source) for rel, source in iter_domain_sources() if rel.startswith("app/")]


def test_every_use_task_call_is_manual_trigger_only():
    sources = _app_sources()
    assert sources, "iter_domain_sources() found nothing under app/ -- the scan itself is broken"

    calls = [call for rel, source in sources for call in _use_task_calls_in_source(rel, source)]
    found_sites = {(rel, lineno) for rel, lineno, _ in calls}

    naive_sites = {
        site for rel, source in sources for site in _naive_use_task_sites_in_source(rel, source)
    }
    missing = naive_sites - found_sites
    assert not missing, (
        "the alias-aware scan lost sites a simpler name/attr-only pass still finds "
        f"(regression in the scan itself, not necessarily the source): {sorted(missing)}"
    )

    violations = []
    for rel, lineno, call in calls:
        dependencies = next((kw.value for kw in call.keywords if kw.arg == "dependencies"), None)
        passes_literal_none = isinstance(dependencies, ast.Constant) and dependencies.value is None
        if not passes_literal_none:
            violations.append(f"{rel}:{lineno}")

    assert violations == [], (
        "these use_task calls do not pass dependencies=None explicitly, so "
        "solara's own default (dependencies=[]) would run them immediately on "
        f"mount instead of only on a click: {violations}"
    )


def test_the_scan_resolves_an_aliased_use_task_import():
    """Fix round 1, finding 1, pinned with a synthetic source rather than a
    real file: ``from solara.lab import use_task as ut`` must not let a real
    violation (``dependencies=[]``, the exact auto-run-on-mount default) hide
    behind an unrecognised bare name."""
    source = (
        "from solara.lab import use_task as ut\n\ndef f(g):\n    return ut(g, dependencies=[])\n"
    )
    calls = _use_task_calls_in_source("app/probe.py", source)
    assert [lineno for _, lineno, _ in calls] == [4]

    _, _, call = calls[0]
    dependencies = next(kw.value for kw in call.keywords if kw.arg == "dependencies")
    assert not (isinstance(dependencies, ast.Constant) and dependencies.value is None)


def test_the_naive_cross_check_would_have_missed_the_same_alias():
    """Documents the boundary of the floor in `test_every_use_task_call_is_manual_
    trigger_only`, so it is not mistaken for something it is not: the naive pass is
    a floor on REGRESSIONS in the alias-aware scan, not a substitute for alias
    resolution -- it is exactly as blind to an aliased import as the scan was
    before fix round 1."""
    source = (
        "from solara.lab import use_task as ut\n\ndef f(g):\n    return ut(g, dependencies=[])\n"
    )
    assert _naive_use_task_sites_in_source("app/probe.py", source) == []
