"""Total validation of a :class:`RunSpec`.

``validate`` is called by the Solara form on every keystroke, while most fields
are still ``None``. It therefore never raises and never rejects a half-filled
spec: it returns field-anchored :class:`Problem` records instead. This replaces
the scattered ``alert.check_input`` chain at ``input_tile.py:245-330`` and the
``raise Exception`` at ``run_15_3_1.py:165-166``.

EXPECTED_DIVERGENCES note -- four divergences from the legacy. Task 17's parity
harness must carry all four.

The legacy had no total validator, so in one sense every :class:`Problem` here is
new. What is recorded below is the narrower set that changes WHICH RUNS ARE
POSSIBLE: a ``fatal=True`` rule refusing a configuration the legacy computed, or a
rule accepting one it refused. The rest are transcriptions of ``input_tile.py``'s
own checks, or non-fatal warnings, which leave the Process button enabled and
therefore change nothing about what runs -- ``state_period_too_short``,
``soc_start_before_cci``, ``land_cover_start_before_cci`` and
``half_custom_land_cover`` are all of that kind, and spec §7 reasoned about the
first explicitly.

1. **Behaviour-changing, and it refuses runs the legacy performed.** The three
   land-cover period rules of :func:`_land_cover_period_problems` have no legacy
   counterpart at all: ``periods.overall`` was the only period whose order was ever
   checked (run_15_3_1.py:165-166). ``land_cover_start_not_before_end`` (fatal) and
   ``land_cover_period_collapses`` (fatal) refuse specs that reached the legacy
   decoders and produced a Sankey with two identically-labelled year columns;
   ``land_cover_start_before_cci`` (warning) reports the clamp. Measured against the
   parity corpus, the fatal pair rejects s04 and s08 -- configurations stage A
   recorded a legacy result for. Spec §7 has no row for any of the three, and the
   trade-off it reasoned about for ``state_period_too_short`` ("Making it fatal
   would refuse configurations the legacy accepts") was not re-applied here; the
   justification is that the failure it prevents is downstream and unattributable,
   at ``sankey_option``, rather than a masked layer.
2. **Behaviour-changing, and it refuses runs the legacy performed.**
   ``soc_period_collapses`` (fatal, :func:`_soc_period_problems`) rejects a SOC
   period lying entirely after the CCI record, where soil_organic_carbon.py:161
   selected a negative band index. Spec §7 mandates it by name, so unlike note 1
   this was a recorded decision; it is here because it still refuses configurations
   the legacy ran -- s04, s08, s24 and s27 in the corpus.
3. **Behaviour-changing.** ``non_finite_climate_coefficient`` (fatal,
   :func:`_climate_problems`) rejects ``nan``/``inf``. Nothing in the legacy ever
   range-checks ``conversion_coef``; only the widget's own ``[0, 1]`` bounds
   constrained it, and a spec read from disk through ``RunSpec.from_dict`` does not
   go through the widget. Values outside ``[0, 1]`` are still accepted, so the entry
   is exactly the two non-finite shapes.
4. **Behaviour-changing, and it WIDENS what is accepted.** ``_matrix_problems``
   tests ``set(flatten()) <= {-1, 0, 1}`` where input_tile.py:310 compared by
   equality, so a legitimate two-valued matrix is no longer rejected. It also adds a
   row-and-column shape check the legacy had nothing equivalent to: a rectangular
   matrix of the wrong rectangle -- the 7x7 default crammed into one 49-value row, a
   transposed custom scheme -- kept the legacy's flatten reading in order and
   misaligned the transition table silently.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from sdg1531.catalog import (
    DISABLED_TRAJECTORIES,
    LAND_COVER_FIRST_YEAR,
    LAND_COVER_MAX_YEAR,
)
from sdg1531.scheme import LandCoverScheme, TransitionMatrix
from sdg1531.spec import (
    CustomLandCoverSource,
    FixedClimate,
    PrecomputedViAsset,
    RunSpec,
    SensorSelection,
)
from sdg1531.tables import DEFAULT_LC_CODES

__all__ = ["Problem", "check_custom_lc_codes", "validate"]

# The top-level `transition_matrix` field has no vocabulary of its own — it only
# ever pairs with the built-in 7-class IPCC scheme (Task 3's default()).
_DEFAULT_LC_CLASS_COUNT = len(DEFAULT_LC_CODES)


@dataclass(frozen=True, slots=True)
class Problem:
    """One validation message.

    ``field`` is a dotted path into ``RunSpec`` so the UI can anchor the message
    under the right widget; ``code`` is the stable key the UI maps to a
    translated string; ``fatal`` says whether the Process button is disabled.
    """

    field: str
    code: str
    message: str
    fatal: bool


def _year(value: object) -> int | None:
    """Return ``value`` when it is a usable year, else ``None``."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _clamp_cci(year: int) -> int:
    """indicator_model.py:156-168, the same clamp ``resolve._clamp_cci`` applies.

    Written out here rather than imported from :mod:`sdg1531.resolve`: ``validate`` runs
    on every keystroke against a half-filled spec, and ``resolve`` raises on one
    (``_require_year``). This module deliberately depends on nothing that can fail.
    """
    return min(max(year, LAND_COVER_FIRST_YEAR), LAND_COVER_MAX_YEAR)


def _base_period_problems(spec: RunSpec) -> tuple[Problem, ...]:
    # run_15_3_1.py:165-166 — `if not (model.start < model.end): raise`
    start = _year(spec.periods.overall.start)
    end = _year(spec.periods.overall.end)
    if start is None or end is None or start < end:
        return ()
    return (
        Problem(
            field="periods.overall.start",
            code="start_not_before_end",
            message="The assessment start year must be earlier than the end year.",
            fatal=True,
        ),
    )


def _soc_period_problems(spec: RunSpec) -> tuple[Problem, ...]:
    """SOC clamps only its end year (soil_organic_carbon.py:12-16)."""
    period = spec.periods.soc.resolve(spec.periods.overall)
    if period is None:
        return ()
    start = _year(period.start)
    end = _year(period.end)
    clamp_start = bool(spec.compatibility.clamp_soc_start_year)
    problems: list[Problem] = []

    if start is not None and start < LAND_COVER_FIRST_YEAR and not clamp_start:
        problems.append(
            Problem(
                field="periods.soc.start",
                code="soc_start_before_cci",
                message=(
                    "The soil organic carbon period starts before the CCI land "
                    f"cover record ({LAND_COVER_FIRST_YEAR}); the years before it "
                    "contribute no land cover transition."
                ),
                fatal=False,
            )
        )

    if start is not None and end is not None:
        # soil_organic_carbon.py:12-14 — the clamped end year
        end_esa = _clamp_cci(end)
        effective_start = max(start, LAND_COVER_FIRST_YEAR) if clamp_start else start
        if end_esa - effective_start < 0:
            # soil_organic_carbon.py:161 — a negative band index
            problems.append(
                Problem(
                    field="periods.soc",
                    code="soc_period_collapses",
                    message=(
                        "The soil organic carbon period lies entirely after the end "
                        f"of the CCI land cover record ({LAND_COVER_MAX_YEAR}), so it "
                        "collapses to nothing."
                    ),
                    fatal=True,
                )
            )

    return tuple(problems)


def _land_cover_period_problems(spec: RunSpec) -> tuple[Problem, ...]:
    """The land cover period, after resolve.py:241-242 clamps BOTH of its endpoints.

    Two holes this closes. First, ``periods.overall`` is the only period whose order is
    checked (:func:`_base_period_problems`), so an inverted land cover override reached
    the decoders unchallenged. Second, because both endpoints go through the CCI clamp, a
    period lying wholly outside the record collapses onto a single year:
    ``_clamp_cci(1980) == _clamp_cci(1985) == 1992``. ``decode_transition_areas`` then
    labels its two year columns identically (stats/decode.py:176) and
    ``stats.plots.sankey_option`` fails on the duplicate label with a bare
    ``ValueError: Grouper for '1992' not 1-dimensional``.
    """
    period = spec.periods.land_cover.resolve(spec.periods.overall)
    start = _year(period.start)
    end = _year(period.end)
    if start is None or end is None:
        return ()

    problems: list[Problem] = []
    if start >= end:
        problems.append(
            Problem(
                field="periods.land_cover.start",
                code="land_cover_start_not_before_end",
                message="The land cover start year must be earlier than the end year.",
                fatal=True,
            )
        )
    elif _clamp_cci(start) >= _clamp_cci(end):
        # NOT soc's `end_esa - start < 0`: a zero-length SOC span is a legal band index
        # of 0 (soil_organic_carbon.py:161), while for land cover equality IS the
        # defect. `>=` also catches the wholly-after-LAND_COVER_MAX_YEAR direction.
        problems.append(
            Problem(
                field="periods.land_cover",
                code="land_cover_period_collapses",
                message=(
                    "The land cover period lies outside the CCI land cover record "
                    f"({LAND_COVER_FIRST_YEAR}-{LAND_COVER_MAX_YEAR}), so both of its "
                    "years clamp to the same one and there is no transition to measure."
                ),
                fatal=True,
            )
        )

    if start < LAND_COVER_FIRST_YEAR:
        # The SOC equivalent (code "soc_start_before_cci") already warns about a shift
        # the user never sees; here the clamped year is written into every transition
        # chart label, so it is the more visible of the two.
        problems.append(
            Problem(
                field="periods.land_cover.start",
                code="land_cover_start_before_cci",
                message=(
                    "The land cover period starts before the CCI land cover record "
                    f"({LAND_COVER_FIRST_YEAR}), so the transition is measured from "
                    f"{LAND_COVER_FIRST_YEAR} instead, and that is the year the chart "
                    "will be labelled with."
                ),
                fatal=False,
            )
        )

    return tuple(problems)


def _state_period_problems(spec: RunSpec) -> tuple[Problem, ...]:
    """productivity.py:198-200 — the baseline filter is empty under four years."""
    period = spec.periods.state.resolve(spec.periods.overall)
    if period is None:
        return ()
    start = _year(period.start)
    end = _year(period.end)
    if start is None or end is None or end - 3 >= start:
        return ()
    return (
        Problem(
            field="periods.state",
            code="state_period_too_short",
            message=(
                "The productivity state period is shorter than four years, so its "
                "baseline is empty and the state layer will be fully masked."
            ),
            fatal=False,
        ),
    )


def _vi_source_problems(spec: RunSpec) -> tuple[Problem, ...]:
    source = spec.vi_source
    if isinstance(source, PrecomputedViAsset):
        # integration.py:80 read a trait that never existed; the arm is offered
        # as data but no UI sets it yet (spec §7).
        return (
            Problem(
                field="vi_source",
                code="unsupported_vi_source",
                message="Pre-computed vegetation index assets are not supported yet.",
                fatal=True,
            ),
        )
    # input_tile.py:254 — `check_input(self.model.sensors, "no sensors")`. `None`
    # is RunSpec's actual default (spec.py) and is the same "nothing chosen yet"
    # state as an empty SensorSelection, so both are reported under one field.
    if source is None or (isinstance(source, SensorSelection) and not source.names):
        return (
            Problem(
                field="vi_source.names",
                code="missing_sensors",
                message="Select at least one sensor.",
                fatal=True,
            ),
        )
    return ()


def _trajectory_problems(spec: RunSpec) -> tuple[Problem, ...]:
    # productivity.py:42-43 raises a bare NameError; parameter/ui.py:34 already
    # marks the option disabled.
    if spec.trajectory not in DISABLED_TRAJECTORIES:
        return ()
    return (
        Problem(
            field="trajectory",
            code="unsupported_trajectory",
            message="The water use efficiency trajectory is not implemented.",
            fatal=True,
        ),
    )


def _climate_problems(spec: RunSpec) -> tuple[Problem, ...]:
    """The custom slider's real domain (``climate_regime.py:29``, ``max=1,
    step=0.01``) is ``[0, 1]``, but nothing in the legacy ever range-checks
    ``conversion_coef`` — only the widget's bounds constrain it, and a spec
    read from disk (``RunSpec.from_dict``) does not go through the widget at
    all. ``nan``/``inf`` are rejected here regardless, since neither can
    describe a real conversion factor and ``sdg1531.naming.run_label`` making
    the label total over them is a survivability fix, not a licence to accept
    them as a spec.
    """
    climate = spec.climate
    if not isinstance(climate, FixedClimate) or math.isfinite(climate.coefficient):
        return ()
    return (
        Problem(
            field="climate.coefficient",
            code="non_finite_climate_coefficient",
            message="The climate conversion coefficient must be a finite number.",
            fatal=True,
        ),
    )


def _custom_scheme_problems(scheme: LandCoverScheme) -> tuple[Problem, ...]:
    problems: list[Problem] = []

    # input_tile.py:303-308 — legacy range-checks only the start codelist, not
    # the end one. Preserved as-is rather than silently widened to both.
    if scheme.start_codes and (min(scheme.start_codes) < 10 or max(scheme.start_codes) > 99):
        problems.append(
            Problem(
                field="land_cover.scheme.start_codes",
                code="custom_code_out_of_range",
                message=(
                    "Custom land cover codes must be two digits (10-99); got "
                    f"{sorted(scheme.start_codes)}."
                ),
                fatal=True,
            )
        )

    # input_tile.py:315-320
    if set(scheme.start_names) != set(scheme.end_names):
        problems.append(
            Problem(
                field="land_cover.scheme",
                code="land_cover_class_mismatch",
                message="The start and end land cover class names must match.",
                fatal=True,
            )
        )

    return tuple(problems)


def _land_cover_problems(spec: RunSpec) -> tuple[Problem, ...]:
    source = spec.land_cover
    if not isinstance(source, CustomLandCoverSource):
        return ()
    problems: list[Problem] = []
    if not source.start_asset:
        problems.append(
            Problem(
                field="land_cover.start_asset",
                code="missing_custom_land_cover_asset",
                message="Select the start land cover asset.",
                fatal=True,
            )
        )
    if not source.end_asset:
        problems.append(
            Problem(
                field="land_cover.end_asset",
                code="missing_custom_land_cover_asset",
                message="Select the end land cover asset.",
                fatal=True,
            )
        )
    if source.start_asset and source.end_asset:
        if source.start_asset == source.end_asset:
            # input_tile.py:259-265
            problems.append(
                Problem(
                    field="land_cover",
                    code="same_land_cover_asset",
                    message="The start and end land cover assets must be different.",
                    fatal=True,
                )
            )
        if source.scheme is None:
            # land_cover.py:40 vs indicator_model.py:232
            problems.append(
                Problem(
                    field="land_cover.scheme",
                    code="half_custom_land_cover",
                    message=(
                        "Custom land cover assets are set without a transition matrix "
                        "file, so their pixel codes are remapped through the default "
                        "IPCC vocabulary."
                    ),
                    fatal=False,
                )
            )
        else:
            problems.extend(_custom_scheme_problems(source.scheme))
    return tuple(problems)


def _water_mask_problems(spec: RunSpec) -> tuple[Problem, ...]:
    """One of the three water-mask arms must be chosen; there is no default.

    The legacy else-branch (land_cover.py:74-81) swallowed an unset mask into a JRC
    one built from ``model.seasonality``, so the form never had to ask. The tagged
    union carries no threshold to fall back on, so ``engine.land_cover`` raises
    instead — and a form-completeness problem that surfaces as an exception several
    seconds into a run is what this module exists to prevent.
    """
    if spec.water_mask is not None:
        return ()
    return (
        Problem(
            field="water_mask",
            code="missing_water_mask",
            message="Select a water mask.",
            fatal=True,
        ),
    )


def _matrix_shape_defect(
    rows: tuple[tuple[int, ...], ...], expected_rows: int, expected_cols: int
) -> str | None:
    """Compare rows and columns, not the total cell count.

    ``TransitionMatrix`` itself now guarantees a rectangular shape
    (``scheme.py``'s ``__post_init__``), so counting cells is not enough: a
    matrix can be perfectly rectangular and still be the *wrong* rectangle — the
    default 7x7 crammed into a single 49-value row, or a custom scheme's matrix
    transposed — and a bare ``len(flatten()) == 49`` check cannot tell the
    difference, because ``flatten()`` reads either shape into the same sequence.
    """
    if len(rows) != expected_rows:
        return f"has {len(rows)} row(s), expected {expected_rows}"
    for index, row in enumerate(rows):
        if len(row) != expected_cols:
            return f"row {index} has {len(row)} value(s), expected {expected_cols}"
    return None


def _matrix_problems(
    matrix: TransitionMatrix, field: str, expected_rows: int, expected_cols: int
) -> tuple[Problem, ...]:
    problems: list[Problem] = []

    # input_tile.py:310 tested `{1, 0, -1} != set(flatten)`, which rejects a
    # legitimate matrix using only two of the three values. Relaxed to a subset.
    foreign = sorted(set(matrix.flatten()) - {-1, 0, 1})
    if foreign:
        problems.append(
            Problem(
                field=field,
                code="invalid_transition_matrix",
                message=f"The transition matrix may only contain -1, 0 and 1; found {foreign}.",
                fatal=True,
            )
        )

    shape_defect = _matrix_shape_defect(matrix.rows, expected_rows, expected_cols)
    if shape_defect is not None:
        problems.append(
            Problem(
                field=field,
                code="invalid_transition_matrix",
                message=f"The transition matrix is the wrong shape: {shape_defect}.",
                fatal=True,
            )
        )

    return tuple(problems)


def _transition_matrix_problems(spec: RunSpec) -> tuple[Problem, ...]:
    problems = list(
        _matrix_problems(
            spec.transition_matrix,
            "transition_matrix",
            _DEFAULT_LC_CLASS_COUNT,
            _DEFAULT_LC_CLASS_COUNT,
        )
    )
    source = spec.land_cover
    if isinstance(source, CustomLandCoverSource) and source.scheme is not None:
        scheme = source.scheme
        problems.extend(
            _matrix_problems(
                scheme.matrix,
                "land_cover.scheme.matrix",
                len(scheme.start_codes),
                len(scheme.end_codes),
            )
        )
    return tuple(problems)


def _aoi_problems(spec: RunSpec) -> tuple[Problem, ...]:
    # input_tile.py:248 — `check_input(self.aoi_model.name, cm.error.no_aoi)`
    if spec.aoi is None:
        return (
            Problem(
                field="aoi",
                code="missing_aoi",
                message="Select an area of interest.",
                fatal=True,
            ),
        )
    return ()


_CHECKS = (
    _base_period_problems,
    _soc_period_problems,
    _land_cover_period_problems,
    _state_period_problems,
    _vi_source_problems,
    _trajectory_problems,
    _climate_problems,
    _land_cover_problems,
    _water_mask_problems,
    _transition_matrix_problems,
    _aoi_problems,
)


def validate(spec: RunSpec) -> tuple[Problem, ...]:
    """Return every problem with ``spec``. Never raises."""
    problems: list[Problem] = []
    for check in _CHECKS:
        try:
            problems.extend(check(spec))
        except Exception as error:  # validate is total; a bug must not break the form
            problems.append(
                Problem(
                    field="",
                    code="internal_error",
                    message=f"{check.__name__} failed: {error!r}",
                    fatal=True,
                )
            )
    return tuple(problems)


def _codes_problem(
    observed: set[int], expected: set[int], field: str, exact: bool
) -> tuple[Problem, ...]:
    if exact:
        if observed == expected:
            return ()
        return (
            Problem(
                field=field,
                code="custom_lc_codes_mismatch",
                message=(
                    "The pixel values of the asset do not match the codes of the "
                    f"transition matrix: asset {sorted(observed)}, "
                    f"matrix {sorted(expected)}."
                ),
                fatal=True,
            ),
        )
    unknown = sorted(observed - expected)
    if not unknown:
        return ()
    return (
        Problem(
            field=field,
            code="custom_lc_codes_not_subset",
            message=(
                "The asset contains pixel values that the transition matrix does "
                f"not define: {unknown}."
            ),
            fatal=True,
        ),
    )


def check_custom_lc_codes(
    scheme: LandCoverScheme,
    start_values: Iterable[int],
    end_values: Iterable[int],
    exact: bool,
) -> tuple[Problem, ...]:
    """Compare observed custom land cover pixel values with the matrix codes.

    The async pre-flight replacing the blocking ``custom_lc_values`` getInfo at
    ``run_15_3_1.py:418-421``, driven from ``input_tile.py:267-298``. ``exact``
    is the legacy ``lc_pixel_check`` switch: True demands set equality, False
    demands a subset.
    """
    return _codes_problem(
        set(start_values), set(scheme.start_codes), "land_cover.start_asset", exact
    ) + _codes_problem(set(end_values), set(scheme.end_codes), "land_cover.end_asset", exact)
