"""The application's single source of truth.

One ``RunSpec`` lives in one reactive. Steps edit their own slice with
``evolve()`` and read their own problems back out of ``validate()``; no step
imports another, and no step stores a derived value.

``STEP_PREFIXES`` is the routing table. ``validate()`` emits ``Problem.field``
as a dotted path that mirrors the spec's own structure, so a step can claim a
subtree by prefix instead of every rule naming its owner. A test asserts the
table covers every field the validator can emit and that no two steps claim the
same one.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from sdg1531.spec import RunSpec
from sdg1531.validate import Problem, validate

__all__ = ("STEP_PREFIXES", "is_runnable", "problems_for")

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


def problems_for(step: str, spec: RunSpec) -> tuple[Problem, ...]:
    """Every problem this step owns.

    Safe on every render: ``validate()`` is total and never raises, for any
    input, including a spec the user has only half filled in.
    """
    prefixes = STEP_PREFIXES[step]
    return tuple(
        p
        for p in validate(spec)
        if any(p.field == prefix or p.field.startswith(prefix + ".") for prefix in prefixes)
    )


def is_runnable(spec: RunSpec) -> bool:
    """No fatal problem anywhere. Warnings do not block a run."""
    return not any(p.fatal for p in validate(spec))
