"""The three `.where()` collapse tables, as ordered data.

Transcribed from the legacy chains, in source order, because the parity harness
(spec §12 Tier 4) compares serialized `ee` graphs as plain strings and
`engine/apply.py` emits one `.where()` per rule in the order given here.

Encoding of a rule's operands: `(name, k)` with k >= 1 is the legacy
`img.eq(k)`; `(name, 0)` is the legacy `img.lt(1)`, which the indicator chain
uses for its last three rows (run_15_3_1.py:406-408). No other predicate occurs.

`classify()` is the one-line statement of the one-out-all-out rule and exists
only as a test oracle for INDICATOR_15_3_1. It never emits a graph, and the UI
layer must not call it (spec §4).

No EXPECTED_DIVERGENCES: the three ``.where()`` collapse chains as ordered data, in
source order. ``engine/apply.py`` emits one node per rule in the order given here,
and the parity harness compares the result node for node -- so a divergence in this
table is a graph divergence, and there is none.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "INDICATOR_15_3_1",
    "PRODUCTIVITY_GPGV1",
    "PRODUCTIVITY_GPGV2",
    "Rule",
    "TruthTable",
    "classify",
]


@dataclass(frozen=True, slots=True)
class Rule:
    """One `.where(predicate, value)` step of a collapse chain."""

    inputs: tuple[tuple[str, int], ...]
    value: int


@dataclass(frozen=True, slots=True)
class TruthTable:
    """An ordered collapse chain plus the band its result is renamed to."""

    rules: tuple[Rule, ...]
    band: str


_PRODUCTIVITY_INPUTS = ("trajectory", "state", "performance")
_INDICATOR_INPUTS = ("productivity", "landcover", "soc")


def _p(trajectory: int, state: int, performance: int, value: int) -> Rule:
    return Rule(
        inputs=tuple(zip(_PRODUCTIVITY_INPUTS, (trajectory, state, performance), strict=True)),
        value=value,
    )


def _i(productivity: int, landcover: int, soc: int, value: int) -> Rule:
    return Rule(
        inputs=tuple(zip(_INDICATOR_INPUTS, (productivity, landcover, soc), strict=True)),
        value=value,
    )


# transcribed from productivity.py:257-332 (productivity_final, the GPGv2 branch
# selected at run_15_3_1.py:184-190)
PRODUCTIVITY_GPGV2 = TruthTable(
    rules=(
        _p(1, 1, 1, 1),
        _p(1, 1, 2, 1),
        _p(1, 2, 1, 1),
        _p(1, 2, 2, 2),
        _p(1, 3, 1, 1),
        _p(1, 3, 2, 1),
        _p(2, 1, 1, 1),
        _p(2, 1, 2, 2),
        _p(2, 2, 1, 1),
        _p(2, 2, 2, 2),
        _p(2, 3, 1, 2),
        _p(2, 3, 2, 2),
        _p(3, 1, 1, 1),
        _p(3, 1, 2, 3),
        _p(3, 2, 1, 3),
        _p(3, 2, 2, 3),
        _p(3, 3, 1, 3),
        _p(3, 3, 2, 3),
    ),
    band="productivity",
)

# transcribed from productivity.py:342-417 (productivity_final_GPG1, the else
# branch at run_15_3_1.py:191-197). Differs from GPGv2 at (1,2,2) and (2,2,1).
PRODUCTIVITY_GPGV1 = TruthTable(
    rules=(
        _p(1, 1, 1, 1),
        _p(1, 1, 2, 1),
        _p(1, 2, 1, 1),
        _p(1, 2, 2, 1),
        _p(1, 3, 1, 1),
        _p(1, 3, 2, 1),
        _p(2, 1, 1, 1),
        _p(2, 1, 2, 2),
        _p(2, 2, 1, 2),
        _p(2, 2, 2, 2),
        _p(2, 3, 1, 2),
        _p(2, 3, 2, 2),
        _p(3, 1, 1, 1),
        _p(3, 1, 2, 3),
        _p(3, 2, 1, 3),
        _p(3, 2, 2, 3),
        _p(3, 3, 1, 3),
        _p(3, 3, 2, 3),
    ),
    band="productivity",
)

# transcribed from run_15_3_1.py:377-409. The legacy chain has no .rename(), so
# its band was literally "constant"; the band below is the §7 divergence.
INDICATOR_15_3_1 = TruthTable(
    rules=(
        _i(3, 3, 3, 3),
        _i(3, 3, 2, 3),
        _i(3, 3, 1, 1),
        _i(3, 2, 3, 3),
        _i(3, 2, 2, 3),
        _i(3, 2, 1, 1),
        _i(3, 1, 3, 1),
        _i(3, 1, 2, 1),
        _i(3, 1, 1, 1),
        _i(2, 3, 3, 3),
        _i(2, 3, 2, 3),
        _i(2, 3, 1, 1),
        _i(2, 2, 3, 3),
        _i(2, 2, 2, 2),
        _i(2, 2, 1, 1),
        _i(2, 1, 3, 1),
        _i(2, 1, 2, 1),
        _i(2, 1, 1, 1),
        _i(1, 3, 3, 1),
        _i(1, 3, 2, 1),
        _i(1, 3, 1, 1),
        _i(1, 2, 3, 1),
        _i(1, 2, 2, 1),
        _i(1, 2, 1, 1),
        _i(1, 1, 3, 1),
        _i(1, 1, 2, 1),
        _i(1, 1, 1, 1),
        _i(1, 0, 0, 1),
        _i(0, 1, 0, 1),
        _i(0, 0, 1, 1),
    ),
    band="indicator_15_3_1",
)


def classify(*classes: int) -> int:
    """One-out-all-out over the three 15.3.1 sub-indicators. Test oracle only.

    Takes exactly three classes — productivity, landcover, soc, in that order —
    and raises otherwise; INDICATOR_15_3_1 has no arity but three, and an oracle
    that answered confidently for any other count would be a trap for whoever
    reuses it later.

    0 is nodata, 1 degraded, 2 stable, 3 improved. A pixel where any
    sub-indicator is missing is nodata, except the three rows the legacy chain
    spells with `.lt(1)`: a single degraded sub-indicator and nothing else
    observed still reports degraded.
    """
    if len(classes) != 3:
        raise ValueError(f"classify() takes exactly 3 sub-indicator classes, got {len(classes)}")
    observed = [value for value in classes if value != 0]
    if len(observed) < len(classes):
        return 1 if observed == [1] else 0
    if 1 in observed:
        return 1
    if 3 in observed:
        return 3
    return 2
