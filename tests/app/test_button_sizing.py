"""Every button-ish call in ``app/`` carries pysepal's right-panel
``small=True`` convention, and (task 30) every one that is not an icon
button also carries ``block=True`` (``docs/guides/solara-app-builder.md``'s
button-sizing table, in the pysepal repo: right-panel content buttons take
``small=True``, adding ``block=True`` for full width).

Two call shapes matter here: ``TaskButtonComponent(...)`` (every compute /
download / add button) and a bare ``rv.Btn(...)`` / ``v.Btn(...)``
(``map_layers.py``'s own remove button, and the two prev/next arrows in
``app/tabs.py``). Both need ``small=True`` in a ~450px right panel -- this
app has no navigation-drawer button to exempt (``page.py``'s
``steps_data=[]`` is empty, so the table's one "never ``small=True``" row
never applies here). ``block=True`` is narrower: the guide's own last row
keeps navigation-drawer icons at their default size, and this app's own
equivalent -- the two prev/next arrows, ``icon=True`` calls -- stay icon
buttons the same way (the repo owner's own brief for this task: "the
prev/next arrows are icon buttons and must stay icon buttons"). That
exemption is read off ``icon=True`` at the call site itself
(``_is_icon_call``), not a hand-typed file/line exemption list, so a NEW
icon button needs no entry added anywhere to be exempted correctly, and a
content button cannot be exempted by mistake just by living in the same
file as one.

Checked the Selects and chips the brief also asked about, and found nothing
to pin: no ``rv.Chip``/``solara.Chip`` call exists anywhere in ``app/``, and
``solara.Select`` has no ``small`` parameter at all (only ``dense``, which
pysepal's own convention table does not mention) -- there is no roster of
non-compliant Selects to derive, because the property this file pins does
not apply to them.

Same two-part lesson ``tests/app/test_task_dependencies.py`` already learned
for ``use_task``, applied here: resolve import bindings (``from ... import
Btn as X``) rather than matching one literal spelling, and hold the
alias-aware scan to a floor set by a simpler, independently-authored
name/attr-only pass, so a regression in the scan itself shows up as a
specific list of missing sites rather than a silent pass. The ``block=True``
check reuses that same alias-aware call list rather than re-scanning, so an
aliased import defeats it exactly as little as it defeats the ``small=True``
check.
"""

from __future__ import annotations

import ast

from hygiene_rules import iter_domain_sources

#: The two call shapes this convention applies to. `ExportLauncher` (used by
#: `app/panels/exports.py`) is deliberately NOT here: it is a pysepal
#: component whose own `small` parameter already defaults to `True`, so
#: exports.py has no bare button call of its own to pin.
_TARGET_NAMES = frozenset({"TaskButtonComponent", "Btn"})


def _aliases_for(tree: ast.Module, target: str) -> frozenset[str]:
    """Local names this module's imports bind to ``target`` -- any ``from
    ... import target as alias``, any source module (a re-export would still
    be caught). Mirrors ``test_task_dependencies.py``'s ``_use_task_aliases``.
    """
    return frozenset(
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == target
    )


def _is_target_call(call: ast.Call, aliases: dict[str, frozenset[str]]) -> str | None:
    """Which of ``_TARGET_NAMES`` this call resolves to, or ``None``.

    An attribute call (``rv.Btn(...)``) needs no alias tracking: an attribute
    access can never rename its own final attribute, so ``rv``/``v`` aliasing
    the MODULE still ends in ``.Btn`` -- the same reasoning
    ``test_task_dependencies.py`` gives for not tracking module aliasing.
    """
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in _TARGET_NAMES:
        return func.attr
    if isinstance(func, ast.Name):
        if func.id in _TARGET_NAMES:
            return func.id
        for name, names in aliases.items():
            if func.id in names:
                return name
    return None


def _button_calls_in_source(rel_path: str, source: str) -> list[tuple[str, int, str, ast.Call]]:
    """Every call in ``source`` that resolves to a target name, alias included."""
    tree = ast.parse(source, filename=rel_path)
    aliases = {name: _aliases_for(tree, name) for name in _TARGET_NAMES}
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = _is_target_call(node, aliases)
            if target is not None:
                calls.append((rel_path, node.lineno, target, node))
    return calls


def _naive_button_sites_in_source(rel_path: str, source: str) -> list[tuple[str, int]]:
    """The plain name/attr-only match -- reimplemented independently rather
    than imported, same reason ``test_task_dependencies.py``'s own naive
    cross-check is: this exists specifically to disagree with the scan above
    if the two ever diverge, which an import would make impossible.
    """
    tree = ast.parse(source, filename=rel_path)
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else None
        attr = func.attr if isinstance(func, ast.Attribute) else None
        if name in _TARGET_NAMES or attr in _TARGET_NAMES:
            sites.append((rel_path, node.lineno))
    return sites


def _app_sources() -> list[tuple[str, str]]:
    """Every ``app/`` source, reusing ``hygiene_rules``'s own file walk --
    same reason ``test_task_dependencies.py``'s identical helper gives."""
    return [(rel, source) for rel, source in iter_domain_sources() if rel.startswith("app/")]


def _literal_true_kwarg(call: ast.Call, name: str) -> bool:
    """Whether ``call`` passes ``name=True`` as a literal, not merely present
    (``name=some_variable`` would not count)."""
    value = next((kw.value for kw in call.keywords if kw.arg == name), None)
    return isinstance(value, ast.Constant) and value.value is True


def _is_icon_call(call: ast.Call) -> bool:
    """An icon-only button (``icon=True``) -- the one call shape task 30's
    ``block=True`` convention deliberately does not apply to (see this
    module's docstring): ``app/tabs.py``'s prev/next arrows."""
    return _literal_true_kwarg(call, "icon")


def test_every_button_call_carries_small_true():
    sources = _app_sources()
    assert sources, "iter_domain_sources() found nothing under app/ -- the scan itself is broken"

    calls = [call for rel, source in sources for call in _button_calls_in_source(rel, source)]
    found_sites = {(rel, lineno) for rel, lineno, _target, _call in calls}

    naive_sites = {
        site for rel, source in sources for site in _naive_button_sites_in_source(rel, source)
    }
    missing = naive_sites - found_sites
    assert not missing, (
        "the alias-aware scan lost sites a simpler name/attr-only pass still finds "
        f"(regression in the scan itself, not necessarily the source): {sorted(missing)}"
    )

    # A floor on the roster itself: today's app/ has seven such call SITES in
    # source (transitions.py, results.py, zonal.py x2, map_layers.py x2,
    # tabs.py's `_NavArrow` -- one call site in source, even though it is
    # INVOKED twice, once per arrow; this is a static scan, not a trace). Not
    # `>= 1` -- a regression that dropped this to one or two sites would
    # still clear a bare non-empty check.
    assert len(calls) >= 7, f"expected at least 7 button call sites, found {len(calls)}: {calls}"

    violations = [
        f"{rel}:{lineno} ({target})"
        for rel, lineno, target, call in calls
        if not _literal_true_kwarg(call, "small")
    ]
    assert violations == [], (
        "these button calls do not pass small=True explicitly, breaking pysepal's "
        f"right-panel button-sizing convention: {violations}"
    )


def test_every_non_icon_button_call_carries_block_true():
    """Task 30's own ask, pysepal's convention table's other half: right-panel
    content buttons take ``block=True`` for full width, alongside the
    ``small=True`` checked above. Icon buttons (``app/tabs.py``'s prev/next
    arrows) are exempted by ``_is_icon_call`` reading ``icon=True`` off the
    call itself, not a hand-typed file/line list -- see this module's
    docstring for why.

    Directly catches both mutations the brief names for this rule: dropping
    ``block=True`` from one outputs button (a violation, naming that exact
    call site), and aliasing the button import in one panel (inherited for
    free from ``_button_calls_in_source``'s own alias resolution -- the same
    reason ``test_every_button_call_carries_small_true`` needs no separate
    alias-import test of its own here either; ``test_the_scan_resolves_an_
    aliased_task_button_component_import``/``..._btn_import`` above already
    prove the shared scan sees through an alias).
    """
    sources = _app_sources()
    calls = [call for rel, source in sources for call in _button_calls_in_source(rel, source)]

    icon_calls = [c for c in calls if _is_icon_call(c[3])]
    content_calls = [c for c in calls if not _is_icon_call(c[3])]

    # A floor on each half of the split, for the same reason the bare `>= 7`
    # above is a floor: today's app/ has exactly one icon call site
    # (`_NavArrow`) and six non-icon ones. A regression that misclassified a
    # real content button as an icon button (exempting it by mistake) or the
    # reverse would still pass a bare non-empty check on either side.
    assert len(icon_calls) == 1, f"expected exactly one icon button call site: {icon_calls}"
    assert len(content_calls) == 6, (
        f"expected exactly six non-icon button call sites: {content_calls}"
    )

    violations = [
        f"{rel}:{lineno} ({target})"
        for rel, lineno, target, call in content_calls
        if not _literal_true_kwarg(call, "block")
    ]
    assert violations == [], (
        "these button calls do not pass block=True explicitly, breaking pysepal's "
        f"right-panel button-sizing convention: {violations}"
    )


def test_the_icon_exemption_does_not_require_block_true():
    """The direct counter-proof for the test above: a synthetic icon button
    with no ``block`` at all must NOT be flagged -- proves the exemption is a
    real branch in the check, not an accident of every icon call in this
    app's own source already happening to pass ``block=True`` anyway.
    """
    source = (
        "from reacton.ipyvuetify import Btn\n\ndef f():\n    return Btn(icon=True, small=True)\n"
    )
    calls = _button_calls_in_source("app/probe.py", source)
    assert len(calls) == 1
    _, _, _, call = calls[0]
    assert _is_icon_call(call)
    assert not _literal_true_kwarg(call, "block")


def test_the_scan_resolves_an_aliased_task_button_component_import():
    """An aliased ``TaskButtonComponent`` import must not let a real
    violation (no ``small=True`` at all) hide behind an unrecognised bare
    name -- the same defect class ``test_task_dependencies.py`` found and
    fixed for ``use_task`` (finding 1, fix round 1).
    """
    source = (
        "from pysepal.solara.components.task_button import TaskButtonComponent as TBC\n\n"
        "def f(**props):\n    return TBC(label='x', **props)\n"
    )
    calls = _button_calls_in_source("app/probe.py", source)
    assert [lineno for _, lineno, _target, _call in calls] == [4]

    _, _, _, call = calls[0]
    small = next((kw.value for kw in call.keywords if kw.arg == "small"), None)
    assert not (isinstance(small, ast.Constant) and small.value is True)


def test_the_scan_resolves_an_aliased_btn_import():
    source = (
        "from reacton.ipyvuetify import Btn as XBtn\n\ndef f():\n    return XBtn(children=['x'])\n"
    )
    calls = _button_calls_in_source("app/probe.py", source)
    assert [lineno for _, lineno, _target, _call in calls] == [4]

    _, _, _, call = calls[0]
    small = next((kw.value for kw in call.keywords if kw.arg == "small"), None)
    assert small is None


def test_the_naive_cross_check_would_have_missed_the_same_alias():
    """Documents the boundary of the floor in
    ``test_every_button_call_carries_small_true``, so it is not mistaken for
    something it is not: the naive pass is a floor on REGRESSIONS in the
    alias-aware scan, not a substitute for alias resolution -- it is exactly
    as blind to an aliased import as the scan was before it resolved bindings.
    """
    source = (
        "from pysepal.solara.components.task_button import TaskButtonComponent as TBC\n\n"
        "def f(**props):\n    return TBC(label='x', **props)\n"
    )
    assert _naive_button_sites_in_source("app/probe.py", source) == []
