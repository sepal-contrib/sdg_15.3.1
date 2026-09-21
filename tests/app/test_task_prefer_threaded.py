"""Every ``solara.lab.use_task`` call in the app runs off the kernel thread.

solara's own docstring: ``prefer_threaded`` "will run coroutine functions as a
task in a thread when threads are available" -- a thread has no kernel
context, which is exactly how GEE work loses the session-backed interface
(``docs/guides/solara-gee-patterns.md``). ``prefer_threaded=False`` is a real
behaviour switch, not bookkeeping: the reviewer flipped every occurrence in
``app/`` from ``False`` to ``True`` (5 files, 6 sites) and 155 of 158 tests
stayed green -- the three that failed did so on incidental timing in
``test_panel_zonal.py``, not a deliberate check. ``grep -rn prefer_threaded
tests/app/`` found nothing before this file.

This scan and its vacuity floor are ``tests/app/test_task_dependencies.py``'s,
copied for a second property over the same call sites rather than
reinvented: alias resolution (``from solara.lab import use_task as ut``
must not hide a real violation behind an unrecognised bare name) and a
cross-check against ``tests/hygiene_rules.py``'s own, independently-authored
``use-task-prefer-threaded`` rule as a floor against the alias-aware scan
itself regressing to fewer sites than a naive name/attr-only pass finds.
"""

from __future__ import annotations

import ast

from hygiene_rules import iter_domain_sources


def _use_task_aliases(tree: ast.Module) -> frozenset[str]:
    """Local names this module's imports bind to ``use_task``. See
    ``test_task_dependencies.py``'s identical helper for why module-level
    aliasing (``import solara.lab as sl``) needs no separate handling."""
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
    ``use-task-prefer-threaded`` rule used before this task's fix.
    Reimplemented here, independently, rather than imported: this exists
    specifically to disagree with the scan above if the two ever diverge,
    which an import would make impossible."""
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


def test_every_use_task_call_passes_prefer_threaded_false():
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
        kw = next((kw for kw in call.keywords if kw.arg == "prefer_threaded"), None)
        passes_literal_false = (
            kw is not None and isinstance(kw.value, ast.Constant) and kw.value.value is False
        )
        if not passes_literal_false:
            violations.append(f"{rel}:{lineno}")

    assert violations == [], (
        "these use_task calls do not pass prefer_threaded=False explicitly, so "
        "solara could run the coroutine in a thread with no kernel context -- "
        f"exactly how GEE work loses the session-backed interface: {violations}"
    )


def test_the_scan_resolves_an_aliased_use_task_import():
    """Mirrors ``test_task_dependencies.py``'s identical regression pin: an
    aliased import must not hide a real ``prefer_threaded`` violation."""
    source = "from solara.lab import use_task as ut\n\ndef f(g):\n    return ut(g, prefer_threaded=True)\n"
    calls = _use_task_calls_in_source("app/probe.py", source)
    assert [lineno for _, lineno, _ in calls] == [4]

    _, _, call = calls[0]
    kw = next(kw for kw in call.keywords if kw.arg == "prefer_threaded")
    assert not (isinstance(kw.value, ast.Constant) and kw.value.value is False)


def test_the_naive_cross_check_would_have_missed_the_same_alias():
    """Documents the boundary of the floor above, so it is not mistaken for
    something it is not: the naive pass is a floor on REGRESSIONS in the
    alias-aware scan, not a substitute for alias resolution -- it is exactly
    as blind to an aliased import as ``hygiene_rules.py``'s rule was before
    this task's fix."""
    source = "from solara.lab import use_task as ut\n\ndef f(g):\n    return ut(g, prefer_threaded=True)\n"
    assert _naive_use_task_sites_in_source("app/probe.py", source) == []
