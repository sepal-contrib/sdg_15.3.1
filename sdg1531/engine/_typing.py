"""Narrow `ee`'s untyped constructor return back to a real type, in one place.

`ee`'s `ComputedObjectMetaclass.__call__` (ee/computedobject.py:23-28) has no return
annotation, so mypy types every `ee.Image(...)` / `ee.FeatureCollection(...)` / ...
construction as `Any`, and that `Any` propagates through everything chained on it.
Left alone, that surfaces as `no-any-return` wherever such a chain is a function's
return expression — the first case is `apply_truth_table`'s `ee.Image(0)` seed.

This module is the one place that says so. Each helper here narrows a specific,
already-known-correct type; none of them suppress a real typing error, and none of
them is a general-purpose escape hatch — add a new one only when a concrete engine
task needs it, named after the type it narrows.
"""

from __future__ import annotations

from typing import Any, cast

import ee

__all__ = ["as_collection", "as_element", "as_image"]


def as_image(obj: Any) -> ee.Image:
    """Narrow an untyped `ee` chain back to `ee.Image`. See the module docstring."""
    return cast("ee.Image", obj)


def as_collection(obj: Any) -> ee.ImageCollection:
    """Narrow an untyped `ee` chain back to `ee.ImageCollection`. See the module docstring."""
    return cast("ee.ImageCollection", obj)


def as_element(obj: Any) -> ee.Element:
    """Narrow an untyped `ee` chain back to `ee.Element`. See the module docstring."""
    return cast("ee.Element", obj)
