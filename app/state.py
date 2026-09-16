"""The application's single source of truth.

One ``RunSpec`` lives in one reactive. Steps edit their own slice with
``evolve()`` and read their own problems back out of ``validate()``; no step
imports another, and no step stores a derived value.

``STEP_PREFIXES`` is the routing table. ``validate()`` emits ``Problem.field``
as a dotted path that mirrors the spec's own structure, so a step can claim a
subtree by prefix instead of every rule naming its owner. A test asserts the
table covers every field the validator can emit and that no two steps claim the
same one.

``render_problems`` is the other half of that: every step used to copy-paste
the same three-line loop over its own ``problems_for()`` result. One copy here
means a change to how a problem is shown (the bold-if-fatal rule, say) reaches
every step at once instead of needing five identical edits.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import solara

from sdg1531.resolve import resolve
from sdg1531.spec import RunSpec
from sdg1531.validate import Problem, validate

__all__ = ("STEP_PREFIXES", "is_runnable", "problems_for", "render_problems")

STEP_PREFIXES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "aoi": ("aoi",),
        "productivity": (
            "vi_source",
            "vegetation_index",
            "trajectory",
            "lceu",
            "productivity_lookup",
            "threshold",
            "climate",
            "periods.trend",
            "periods.state",
            "periods.performance",
        ),
        "land_cover": (
            "land_cover",
            "transition_matrix",
            "water_mask",
            "periods.land_cover",
        ),
        "soc": ("periods.soc",),
        "run": ("periods.overall", ""),
    }
)


def _owns(prefix: str, field: str) -> bool:
    """True when `prefix` claims `field`: itself, or one of its dotted children.

    The one place this rule is written. ``problems_for`` and the coverage test in
    ``tests/app/test_state.py`` both call it, rather than each keeping its own copy
    that could drift out of sync with the other.
    """
    return field == prefix or field.startswith(prefix + ".")


def problems_for(step: str, spec: RunSpec) -> tuple[Problem, ...]:
    """Every problem this step owns.

    Safe on every render: ``validate()`` is total and never raises, for any
    input, including a spec the user has only half filled in. ``step`` is not:
    an unknown step name is a programming error, not a half-filled form, and
    ``STEP_PREFIXES[step]`` raises ``KeyError`` for it rather than silently
    returning no problems, which would hide the bug behind a step that simply
    never shows any.
    """
    prefixes = STEP_PREFIXES[step]
    return tuple(p for p in validate(spec) if any(_owns(prefix, p.field) for prefix in prefixes))


def render_problems(step: str, spec: RunSpec) -> None:
    """Render every problem ``step`` owns: bold and blocking if fatal, plain
    text otherwise. Not a ``@solara.component`` -- it renders no hook of its
    own, so a plain function called from inside a step's render body is
    enough, the same way each step called ``solara.Markdown`` in a loop
    directly before this was extracted.
    """
    for problem in problems_for(step, spec):
        solara.Markdown(f"**{problem.message}**" if problem.fatal else problem.message)


def is_runnable(spec: RunSpec) -> bool:
    """No fatal problem anywhere, AND the spec actually resolves.

    ``validate()`` alone is not enough: it has no rule for every field
    ``resolve()`` requires. ``periods.overall`` is the standing example --
    left unset, it propagates as ``None`` through every sub-period that falls
    back to it, and ``validate()`` reports nothing wrong. ``resolve()`` is not
    total the way ``validate()`` is, though: an overall period with neither
    endpoint set raises ``SpecError`` deriving the first year it needs, but
    one with a START and no END yet -- a state the Run step's two independent
    year Selects reach naturally between picking one and the other -- reaches
    ``_integration_period()``'s ``max()`` over an all-``None`` tuple and
    raises a bare ``ValueError`` instead (measured, not assumed: see
    ``tests/app/test_step_run.py``). This is called on every render exactly
    like ``validate()`` is, so it has to be just as total: ANY exception from
    ``resolve()`` means "not runnable" here, matching ``validate()``'s own
    "a bug must not break the form" catch-all rather than special-casing each
    shape ``resolve()`` can fail on.

    Asking ``resolve()`` itself, rather than reimplementing its requirements
    here, is what keeps this guard from rotting out of sync with the engine --
    and it costs nothing to ask on every render: ``resolve()`` imports no
    ``ee`` and touches no network.
    """
    if any(p.fatal for p in validate(spec)):
        return False
    try:
        resolve(spec)
    except Exception:
        return False
    return True
