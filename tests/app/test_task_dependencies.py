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
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"


def _use_task_calls() -> list[tuple[Path, int, ast.Call]]:
    """Every call anywhere under ``app/`` whose callee is named ``use_task``.

    Matches by attribute/name alone (``solara.lab.use_task(...)``, or a bare
    ``use_task(...)`` under any import alias) rather than a hand-typed list of
    files and line numbers, so a new call site is covered automatically.
    """
    calls: list[tuple[Path, int, ast.Call]] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "use_task":
                calls.append((path, node.lineno, node))
    return calls


def test_every_use_task_call_is_manual_trigger_only():
    calls = _use_task_calls()
    # A scan that silently found nothing would make the loop below pass
    # vacuously. Six sites are known to exist today (results.py,
    # map_layers.py, transitions.py, zonal.py x2); this is a floor that
    # catches the SCAN breaking, not that roster re-typed as an assertion.
    assert len(calls) >= 1, "found no use_task calls at all -- the scan itself is broken"

    violations = []
    for path, lineno, call in calls:
        dependencies = next((kw.value for kw in call.keywords if kw.arg == "dependencies"), None)
        passes_literal_none = isinstance(dependencies, ast.Constant) and dependencies.value is None
        if not passes_literal_none:
            violations.append(f"{path.relative_to(APP_ROOT.parent)}:{lineno}")

    assert violations == [], (
        "these use_task calls do not pass dependencies=None explicitly, so "
        "solara's own default (dependencies=[]) would run them immediately on "
        f"mount instead of only on a click: {violations}"
    )
