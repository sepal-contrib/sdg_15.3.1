"""Total validation of a :class:`RunSpec`.

``validate`` is called by the Solara form on every keystroke, while most fields
are still ``None``. It therefore never raises and never rejects a half-filled
spec: it returns field-anchored :class:`Problem` records instead. This replaces
the scattered ``alert.check_input`` chain at ``input_tile.py:245-330`` and the
``raise Exception`` at ``run_15_3_1.py:165-166``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sdg1531.catalog import LAND_COVER_FIRST_YEAR, LAND_COVER_MAX_YEAR
from sdg1531.spec import RunSpec, SensorSelection

__all__ = ["Problem", "validate"]


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
        end_esa = min(max(end, LAND_COVER_FIRST_YEAR), LAND_COVER_MAX_YEAR)
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
    # input_tile.py:254 — `check_input(self.model.sensors, "no sensors")`. `None`
    # is RunSpec's actual default (spec.py) and is the same "nothing chosen yet"
    # state as an empty SensorSelection, so both are reported under one field.
    source = spec.vi_source
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
    _state_period_problems,
    _vi_source_problems,
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
