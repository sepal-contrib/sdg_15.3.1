"""The one compiler for all three `.where()` collapses.

Transcribed from the shape of productivity.py:257-332 (and :342-417) and
run_15_3_1.py:377-409, which are three copies of the same chain:

    ee.Image(0)
      .where(a.eq(i).And(b.eq(j)).And(c.eq(k)), v)   # once per rule, in order
      ...
      .rename(band)

`.And()` nests left-associatively, and the rules are emitted in the order the
table lists them: both are what keeps the encoded graph byte-identical to the
legacy one. A rule's class 0 emits `.lt(1)`, matching run_15_3_1.py:406-408; every
other class k emits `.eq(k)`.

The UI layer must never call this; a Tier-0 guard enforces it.

No EXPECTED_DIVERGENCES: the emitter for ``truth_table``'s rules, one ``.where()`` per
rule in the order given. Every graph it builds is byte-compared against the legacy
by the parity harness, so it has no room to diverge silently.
"""

from __future__ import annotations

from collections.abc import Sequence

import ee

from sdg1531.engine._typing import as_image
from sdg1531.truth_table import TruthTable

__all__ = ["apply_truth_table"]


def apply_truth_table(images: Sequence[ee.Image], table: TruthTable, band_name: str) -> ee.Image:
    """Collapse `images` through `table` into a single band named `band_name`.

    `images` are positional: image i is tested against operand i of every rule.
    The caller adds the terminal cast (`.uint8()`) and any water masking, so
    that those stay where the legacy code put them.

    The caller also does its own band selection. `productivity.py:253-255` binds
    `trajectory.select("trajectory")`, `state.select("state")` and
    `performance.select("performance")` before the chain, whereas
    `run_15_3_1.py:379-408` tests the images exactly as passed. So
    `engine/productivity.py` hands in selected images and appends `.uint8()`,
    and `engine/indicator.py` hands in the images whole. This function never
    calls `.select()` and never casts.
    """
    if not table.rules:
        raise ValueError("truth table has no rules")

    names = tuple(name for name, _ in table.rules[0].inputs)
    for rule in table.rules:
        if tuple(name for name, _ in rule.inputs) != names:
            raise ValueError(f"operand order changes mid-table: {rule.inputs}")
    if len(images) != len(names):
        raise ValueError(f"table expects {len(names)} images, got {len(images)}")

    # as_image() narrows the seed once so the whole chain below stays typed as
    # ee.Image, not Any (sdg1531/engine/_typing.py).
    result = as_image(ee.Image(0))
    for rule in table.rules:
        predicate = None
        for image, (_name, cls) in zip(images, rule.inputs, strict=True):
            term = image.lt(1) if cls == 0 else image.eq(cls)
            predicate = term if predicate is None else predicate.And(term)
        result = result.where(predicate, rule.value)

    return result.rename(band_name)
