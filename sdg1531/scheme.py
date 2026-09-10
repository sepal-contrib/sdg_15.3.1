"""The land-cover vocabulary and the transition matrix, as frozen values.

Replaces indicator_model.py:172-266 (nine properties, five of which re-read the
CSV from disk through custom_lc_matrix_list :172-174) and its csv_reader
:315-321. Pure: no file I/O, no ee, no global RNG.

EXPECTED_DIVERGENCES note -- two divergences from the legacy. Task 17's parity
harness must carry both:

1. **Behaviour-changing, scoped to the LABEL.** :meth:`TransitionMatrix.is_default`
   compares by VALUE. indicator_model.py:305 compared the shared module-level list
   with itself -- ``:53`` stores it without a copy -- so ``custom_matrix`` was
   permanently False and a run whose only change was an edited matrix was labelled
   "default", silently overwriting the previous run's result directory. It reaches
   nothing but ``naming.run_label``, whose own divergence is
   ``sdg1531/naming.py``'s note 1.
2. **Behaviour-changing, at CONSTRUCTION.** ``TransitionMatrix.__post_init__``
   rejects a ragged matrix. The legacy had no such type: a matrix was a list of
   lists read off a CSV, ``flatten()`` read it row by row regardless of length, and
   a short or long row shifted every value after it -- so the flattened sequence
   zipped against ``class_combinations`` in ``resolve.py`` came out misaligned
   rather than refused. ``RunSpec.from_dict`` is the one path that can hand this
   constructor a shape straight off disk without passing through
   ``sdg1531.validate``, which is why the check is on the constructor and not only
   in the validator (``validate._matrix_shape_defect`` catches the rectangular-but-
   wrong shapes that this one cannot see).
"""

from __future__ import annotations

import csv
import io
import random
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sdg1531.errors import CustomMatrixError
from sdg1531.palette import CSS4_HEX
from sdg1531.tables import (
    DEFAULT_LC_CLASS_NAMES,
    DEFAULT_LC_CODES,
    DEFAULT_LC_COLORS,
    DEFAULT_TRANSITION_MATRIX,
)

__all__ = [
    "LandCoverScheme",
    "TransitionMatrix",
    "parse_custom_matrix_csv",
    "read_matrix_csv",
]

# transcribed from indicator_model.py:186 / :196
_NAME_SCRUB = re.compile(r"[^a-zA-Z -]+")

# transcribed from indicator_model.py:249
_PALETTE_SEED = 100


def _scrub(value: str) -> str:
    """indicator_model.py:187 — ``re.sub(pattern, "", x.strip())``.

    ``.strip()`` runs on the raw value *before* the substitution, so a run of
    scrubbed characters that borders surviving text can leave a new leading or
    trailing space behind — e.g. ``"50% forest"`` strips to itself (no edge
    whitespace), then loses the leading ``"50%"``, leaving ``" forest"``. This is
    the legacy behaviour (indicator_model.py:186) and is kept on purpose, not a
    bug to "fix" with a second strip.
    """
    return _NAME_SCRUB.sub("", value.strip())


@dataclass(frozen=True, slots=True)
class TransitionMatrix:
    """The land-cover transition matrix, frozen over tuples.

    widget/transition_matrix.py:46 index-assigns into the module-level
    ``pm.default_trans_matrix``; under Solara that is one user's edit leaking into
    every other session in the worker (spec §7). Editing goes through
    :meth:`with_cell`, which returns a new instance.
    """

    rows: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        """Coerce ``rows`` to a tuple of tuples of ints, and reject a ragged shape.

        Without the coercion, ``TransitionMatrix(rows=[[0, -1], [1, 0]])`` is
        accepted silently: the instance is frozen but its rows are still mutable
        lists, and :meth:`is_default` then compares ``list != tuple`` and reports
        False for a semantically-default matrix. ``from_list`` already does the
        right thing, but nothing forced every caller (Task 5's deserializer among
        them) through it — this makes the constructor itself safe.

        Without the shape check, a ragged matrix (rows of unequal length) was
        accepted too. :meth:`flatten` reads it row by row regardless, so a short
        or long row shifts every value after it — and because that flattened
        sequence is zipped against ``LandCoverScheme.class_combinations`` in
        ``resolve.py``, the result is not a loud error but a silently misaligned
        transition table. Deserializing a spec (``_matrix_from_json``) is the one
        path that can hand this constructor a ragged shape read straight off
        disk, bypassing ``sdg1531.validate`` entirely.
        """
        rows = tuple(tuple(int(value) for value in row) for row in self.rows)
        object.__setattr__(self, "rows", rows)
        lengths = {len(row) for row in rows}
        if len(lengths) > 1:
            raise ValueError(
                f"TransitionMatrix rows must all be the same length; got lengths {sorted(lengths)}"
            )

    @classmethod
    def default(cls) -> TransitionMatrix:
        """transcribed from parameter/matrix.py:1-17."""
        return cls(rows=DEFAULT_TRANSITION_MATRIX)

    def flatten(self) -> tuple[int, ...]:
        """Row-major. transcribed from indicator_model.py:239-241."""
        return tuple(item for sublist in self.rows for item in sublist)

    def is_default(self) -> bool:
        """By value, not identity — indicator_model.py:305 compared the shared
        module-level list with itself and was therefore permanently False."""
        return self.rows == DEFAULT_TRANSITION_MATRIX

    def with_cell(self, row: int, col: int, value: int) -> TransitionMatrix:
        if not 0 <= row < len(self.rows):
            raise IndexError(f"row {row} out of range for a {len(self.rows)}-row matrix")
        target = self.rows[row]
        if not 0 <= col < len(target):
            raise IndexError(f"column {col} out of range for a {len(target)}-column row")
        new_row = (*target[:col], int(value), *target[col + 1 :])
        return TransitionMatrix(rows=(*self.rows[:row], new_row, *self.rows[row + 1 :]))

    def to_list(self) -> list[list[int]]:
        return [list(row) for row in self.rows]

    @classmethod
    def from_list(cls, rows: Iterable[Iterable[int | str]]) -> TransitionMatrix:
        return cls(rows=tuple(tuple(int(value) for value in row) for row in rows))


@dataclass(frozen=True, slots=True, kw_only=True)
class LandCoverScheme:
    """The start/end class vocabulary plus the matrix that scores its transitions.

    Replaces indicator_model.py:177-266. ``is_custom`` is the single place the
    "did the user supply a CSV" question is answered; the legacy asked it six
    times, in six duplicated ``if self.start_lc and self.end_lc and
    self.custom_matrix_file`` tests that could disagree.

    ``kw_only=True``: five fields of the same two shapes (``tuple[str, ...]`` /
    ``tuple[int, ...]``) invite a transposed positional call that Python's type
    checker cannot catch. Keyword-only construction is the only thing that makes
    that mistake fail loudly instead of silently swapping start and end classes.
    """

    start_names: tuple[str, ...]
    start_codes: tuple[int, ...]
    end_names: tuple[str, ...]
    end_codes: tuple[int, ...]
    matrix: TransitionMatrix
    is_custom: bool = field(default=False)

    @classmethod
    def default(cls, matrix: TransitionMatrix | None = None) -> LandCoverScheme:
        """The seven IPCC classes. transcribed from parameter/matrix.py:19-28."""
        return cls(
            start_names=DEFAULT_LC_CLASS_NAMES,
            start_codes=DEFAULT_LC_CODES,
            end_names=DEFAULT_LC_CLASS_NAMES,
            end_codes=DEFAULT_LC_CODES,
            matrix=matrix if matrix is not None else TransitionMatrix.default(),
            is_custom=False,
        )

    @property
    def class_combinations(self) -> tuple[int, ...]:
        """transcribed from indicator_model.py:221-227 — CSV order, start-major."""
        return tuple(
            int(str(lc_code_start) + str(lc_code_end))
            for lc_code_start in self.start_codes
            for lc_code_end in self.end_codes
        )

    @property
    def combination_labels(self) -> tuple[str, ...]:
        """transcribed from run_15_3_1.py:217-219 — parallel to class_combinations."""
        return tuple(i + "_" + j for i in self.start_names for j in self.end_names)

    @property
    def code_ordered_names(self) -> tuple[str, ...]:
        """Start-class names sorted by their code. transcribed from
        indicator_model.py:251-262. Duplicate codes collapse, exactly as the dict
        comprehension there does."""
        # start_codes/start_names are always built pairwise from the same source
        # (.default()'s DEFAULT_LC_CODES/DEFAULT_LC_CLASS_NAMES, both length 7, or
        # parse_custom_matrix_csv's one-code-per-row loop) — a length mismatch here
        # is a real bug, so strict=True fails loudly instead of truncating silently.
        by_code = dict(zip(self.start_codes, self.start_names, strict=True))
        return tuple(dict(sorted(by_code.items())).values())

    def palette(self) -> tuple[str, ...]:
        """transcribed from indicator_model.py:246-250.

        The legacy seeds the process-wide RNG (``random.seed(100)``) and samples
        ``matplotlib.colors.cnames`` values; a private ``Random`` reproduces the
        same sequence without that side effect.
        """
        if not self.is_custom:
            return tuple(DEFAULT_LC_COLORS.values())
        return tuple(random.Random(_PALETTE_SEED).sample(CSS4_HEX, len(self.start_names)))

    def color_by_class(self) -> dict[str, str]:
        """transcribed from indicator_model.py:251-266 — colours land on the
        code-sorted names, while everything else keeps CSV order."""
        if not self.is_custom:
            return dict(DEFAULT_LC_COLORS)
        # code_ordered_names can be *shorter* than palette() when two start classes
        # share a code — code_ordered_names collapses duplicate keys (see above) but
        # palette() samples len(start_names) colours regardless. The legacy dict
        # comprehension it replaces truncates the same way, so strict=False here
        # preserves that behaviour rather than newly raising on input it accepted.
        return dict(zip(self.code_ordered_names, self.palette(), strict=False))

    def code_to_name_start(self) -> dict[int, str]:
        """transcribed from run_15_3_1.py:266 — pairs by position, not by sort."""
        # same invariant as code_ordered_names: one code per start class, so a
        # mismatch means the scheme was built wrong, not that legacy input arrived.
        return dict(zip(self.start_codes, self.start_names, strict=True))


def read_matrix_csv(text: str) -> list[list[str]]:
    """Split a transition-matrix CSV into rows of raw cells.

    Replaces indicator_model.py:315-321 (``csv_reader``), whose only difference is
    that it opened a path. The shipped template utils/ipccsx_matrix.csv is CRLF
    with no final newline, which is why this goes through ``csv`` rather than
    ``str.splitlines``.
    """
    return list(csv.reader(io.StringIO(text, newline="")))


def parse_custom_matrix_csv(rows: Sequence[Sequence[str]]) -> LandCoverScheme:
    """Build a custom scheme from the rows read by :func:`read_matrix_csv`.

    One pass over the CSV, replacing the five properties at indicator_model.py
    :179, :185, :195, :205 and :214 that each re-read the file.

    Layout: row 0 is ``["Land cover", <end year>, *end class names]``; row 1 is
    ``[<start year>, "Code", *end class codes]``; every later row is
    ``[<start class name>, <start class code>, *transition values]``.
    """
    if len(rows) < 3:
        raise CustomMatrixError(
            "a custom transition matrix needs at least three rows: names, codes, and "
            f"one row per start class (got {len(rows)})"
        )

    header, code_row, *data_rows = rows

    # indicator_model.py:185-187
    end_names = tuple(_scrub(value) for value in header[2:])
    # indicator_model.py:195-197
    start_names = tuple(_scrub(row[0]) if row else "" for row in data_rows)
    if not end_names or not start_names:
        raise CustomMatrixError("the matrix declares no land cover classes")

    # indicator_model.py:206-207
    try:
        end_codes = tuple(int(value) for value in code_row[2:])
    except ValueError as exc:
        raise CustomMatrixError(f"end class code is not an integer: {exc}") from exc
    if len(end_codes) != len(end_names):
        raise CustomMatrixError(
            f"the matrix declares {len(end_names)} class names but {len(end_codes)} class codes"
        )

    start_codes: list[int] = []
    matrix_rows: list[tuple[int, ...]] = []
    for index, row in enumerate(data_rows, start=1):
        if len(row) < 2:
            raise CustomMatrixError(f"row {index} has no class code")
        # indicator_model.py:215-216
        try:
            start_codes.append(int(row[1]))
        except ValueError as exc:
            raise CustomMatrixError(
                f"start class code is not an integer in row {index}: {row[1]!r}"
            ) from exc
        # indicator_model.py:179 (custom_transition_matrix) + :233-237 (flatten)
        values = row[2:]
        if len(values) != len(end_codes):
            raise CustomMatrixError(
                f"row {index} has {len(values)} transition values, expected {len(end_codes)}"
            )
        try:
            matrix_rows.append(tuple(int(value) for value in values))
        except ValueError as exc:
            raise CustomMatrixError(
                f"transition value is not an integer in row {index}: {exc}"
            ) from exc

    return LandCoverScheme(
        start_names=start_names,
        start_codes=tuple(start_codes),
        end_names=end_names,
        end_codes=end_codes,
        matrix=TransitionMatrix(rows=tuple(matrix_rows)),
        is_custom=True,
    )
