"""Narrow `ee`'s untyped constructor return back to a real type, in one place.

`ee`'s `ComputedObjectMetaclass.__call__` (ee/computedobject.py:23-28) has no return
annotation, so mypy types every `ee.Image(...)` / `ee.FeatureCollection(...)` / ...
construction as `Any`, and that `Any` propagates through everything chained on it.
Left alone, that surfaces as `no-any-return` wherever such a chain is a function's
return expression — the first case is `apply_truth_table`'s `ee.Image(0)` seed.

This module is the one place that says so, for engine-wide narrowing of both kinds:

* **cast-based** — `as_image` / `as_collection` / `as_element` narrow a specific,
  already-known-correct type. None of them suppress a real typing error, and none is
  a general-purpose escape hatch — add one only when a concrete engine task needs it,
  named after the type it narrows.
* **raise-based** — `require_int` / `require_float` narrow an `X | None` that the
  resolve step guarantees is set but the type system cannot see. These raise
  `SpecError`, so unlike the casts they are port-only behaviour with NO legacy
  counterpart: the legacy passes an unset value straight into the `ee` graph. Every
  engine module that narrows a resolved field routes through here, so Task 17's parity
  harness has ONE place to enumerate these raises and one docstring pattern to match,
  rather than a copy per module.
"""

from __future__ import annotations

from typing import Any, cast

import ee

from sdg1531.errors import SpecError

__all__ = [
    "as_collection",
    "as_element",
    "as_image",
    "require_float",
    "require_int",
]


def as_image(obj: Any) -> ee.Image:
    """Narrow an untyped `ee` chain back to `ee.Image`. See the module docstring."""
    return cast("ee.Image", obj)


def as_collection(obj: Any) -> ee.ImageCollection:
    """Narrow an untyped `ee` chain back to `ee.ImageCollection`. See the module docstring."""
    return cast("ee.ImageCollection", obj)


def as_element(obj: Any) -> ee.Element:
    """Narrow an untyped `ee` chain back to `ee.Element`. See the module docstring."""
    return cast("ee.Element", obj)


def require_int(value: int | None, what: str) -> int:
    """Narrow a resolved integer field — a `Period` bound — before it is used as a number.

    `Period.start`/`.end` stay `int | None` for the half-filled form (spec.py), and
    `resolve()` guarantees the periods it emits have both set, but nothing in the type
    system says so. Raising here is port-only behaviour; see the module docstring.
    """
    if value is None:
        raise SpecError(f"{what} must be resolved before the ee graph can be built")
    return value


def require_float(value: float | None, what: str) -> float:
    """Narrow a resolved float field — `spec.threshold`. See `require_int`."""
    if value is None:
        raise SpecError(f"{what} must be resolved before the ee graph can be built")
    return value
