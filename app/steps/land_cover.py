"""Land cover configuration.

Owns: land_cover, transition_matrix, water_mask and the land-cover period.
``transition_matrix`` has no control here yet.

The ``land_cover`` union keeps its two arms apart: ``EsaCciSource`` has no
fields, while ``CustomLandCoverSource`` needs a start and an end asset before
it is usable, so the pickers render only when the custom arm is chosen --
leaving it selectable but permanently unsatisfiable would move
``missing_custom_land_cover_asset`` from a validate() problem into a dead end.
The picker is pysepal's ``AssetSelectComponent``, which validates that the
chosen asset is an IMAGE, as the legacy's ``sw.AssetSelect`` did
(``select_lc.py:17``).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

import solara
from pysepal.solara.components.inputs.asset_select import AssetSelectComponent
from pysepal.solara.notifications import use_notifications

from app.message import msg
from app.panels.problems import ProblemsAlert
from app.steps.period_override import PeriodOverrideControl
from sdg1531.catalog import L4_START
from sdg1531.scheme import LandCoverScheme
from sdg1531.spec import (
    CustomLandCoverSource,
    EsaCciSource,
    JrcSeasonalityMask,
    PeriodOverride,
    RunSpec,
)
from sdg1531.stats.api import fetch_distinct_pixel_values
from sdg1531.validate import check_custom_lc_codes

__all__ = ("LandCoverStep",)

_SOURCE_KEYS = ("esa", "custom")


def _source_labels() -> dict[str, str]:
    """Map each land-cover source key to its translated display label.

    Rebuilt on every render, not cached: ``msg()`` subscribes to the current
    locale, so a cached copy would not update when the language changes.
    """
    return {key: msg(f"land_cover.{key}") for key in _SOURCE_KEYS}


def _asset_value(asset_id: str) -> dict[str, Any] | None:
    """The dict shape ``AssetSelectComponent`` reads and writes, or ``None``
    for "nothing chosen" -- the shape its own ``select_asset`` builds for a
    fresh pick, so a persisted id round-trips through the same constructor a
    live selection would produce."""
    if not asset_id:
        return None
    return {"asset_id": asset_id, "type": None, "column": "ALL", "value": None}


def _asset_id(value: dict[str, Any] | None) -> str:
    """The plain asset-id string ``CustomLandCoverSource`` holds, out of the
    component's dict -- ``None`` (cleared, or still failing validation) maps
    to ``""``, exactly what an emptied text field used to write."""
    return (value or {}).get("asset_id") or ""


def _scheme_for_pixel_check(custom_source: CustomLandCoverSource, spec: RunSpec) -> LandCoverScheme:
    """The classification a custom asset's pixel values are checked against.

    Mirrors ``sdg1531.resolve._scheme()``'s own fallback exactly -- that
    function is private, and ``resolve()`` itself needs a fully populated
    spec, which a half-filled form is not required to be -- so this re-derives
    the two-line fallback locally instead of importing it.
    ``tests/app/test_step_land_cover.py``'s
    ``test_the_pixel_check_scheme_fallback_matches_resolve`` pins the two
    together so they cannot silently diverge.
    """
    return custom_source.scheme or LandCoverScheme.default(matrix=spec.transition_matrix)


async def _check_pixel_values(
    gee_interface: Any,
    notifications: Any,
    scheme: LandCoverScheme,
    start_asset: str,
    end_asset: str,
) -> None:
    """Fetch both assets' pixel values and report any mismatch with ``scheme``.

    The pre-flight ``validate()`` cannot run (see this module's docstring) --
    this is it, triggered once a picker settles on a real asset rather than on
    every render, and reporting through ``notifications`` rather than a
    ``Problem`` because that is the only route left once the check has
    already happened.
    """
    start_values = await fetch_distinct_pixel_values(gee_interface, start_asset)
    end_values = await fetch_distinct_pixel_values(gee_interface, end_asset)
    for problem in check_custom_lc_codes(scheme, start_values, end_values, exact=False):
        notifications.error(problem.message)


@solara.component
def LandCoverStep(spec: solara.Reactive[RunSpec], gee_interface: Any = None) -> None:
    def _seed_water_mask() -> None:
        # `None` is the domain's genuinely-unset state (`missing_water_mask`,
        # fatal) -- not one of the three real arms -- so it is the one case
        # this control may safely commit a default for, the way
        # productivity.py's `_seed_threshold` does for its own unset field.
        # `RunSpec.water_mask`'s own default_factory is
        # `JrcSeasonalityMask(threshold=8)`; seed exactly that.
        if spec.value.water_mask is None:
            spec.set(spec.value.evolve(water_mask=JrcSeasonalityMask(threshold=8)))

    solara.use_effect(_seed_water_mask, [])

    notifications = use_notifications()

    # `dependencies=None`: this never auto-runs on mount (unlike
    # `AssetSelectComponent`'s own internal listing task) -- it is fired by
    # name, below, only once both assets are actually set. Registered here,
    # unconditionally, so the hook exists on every render regardless of which
    # land_cover arm is current; only the call site is conditional.
    task = solara.lab.use_task(
        _check_pixel_values, dependencies=None, raise_error=False, prefer_threaded=False
    )

    def _report_pixel_check_failure() -> None:
        if task.error:
            notifications.error(str(task.exception))

    solara.use_effect(_report_pixel_check_failure, [task.finished, task.error])

    # The title is the PARAMS section header's (`app/panels/params.py`);
    # this step renders only its own controls.

    current = spec.value

    source_labels = _source_labels()
    source_by_label = {label: key for key, label in source_labels.items()}
    is_custom = isinstance(current.land_cover, CustomLandCoverSource)

    solara.Select(
        label=msg("land_cover.source"),
        value=source_labels["custom" if is_custom else "esa"],
        values=list(source_labels.values()),
        on_value=lambda label: spec.set(
            spec.value.evolve(
                land_cover=(
                    CustomLandCoverSource(start_asset="", end_asset="")
                    if source_by_label[label] == "custom"
                    else EsaCciSource()
                )
            )
        ),
    )

    def _set_period(new: PeriodOverride) -> None:
        spec.set(spec.value.evolve(periods=replace(spec.value.periods, land_cover=new)))

    # Same range and the same "no invented default" rule as `soc.py`'s own
    # control -- `periods.land_cover` is an OPTIONAL override too, and
    # `resolve()` derives the window from `periods.overall` when it is unset.
    # The legacy's deleted `PickerLineLC` used this exact
    # `range(sensor_max_year, L4_start - 1, -1)`, the same one
    # `PickerLineSOC` did.
    period_years = list(range(date.today().year - 1, L4_START - 1, -1))

    PeriodOverrideControl(
        override=current.periods.land_cover,
        overall=current.periods.overall,
        years=period_years,
        start_label=msg("land_cover.period_start"),
        end_label=msg("land_cover.period_end"),
        on_change=_set_period,
    )

    if isinstance(current.land_cover, CustomLandCoverSource):
        custom_source = current.land_cover

        def _maybe_check_pixel_values(start_asset: str, end_asset: str) -> None:
            if not (start_asset and end_asset):
                return
            scheme = _scheme_for_pixel_check(custom_source, current)
            task(gee_interface, notifications, scheme, start_asset, end_asset)

        def _on_start_value(value: dict[str, Any] | None) -> None:
            new_start = _asset_id(value)
            spec.set(spec.value.evolve(land_cover=replace(custom_source, start_asset=new_start)))
            _maybe_check_pixel_values(new_start, custom_source.end_asset)

        def _on_end_value(value: dict[str, Any] | None) -> None:
            new_end = _asset_id(value)
            spec.set(spec.value.evolve(land_cover=replace(custom_source, end_asset=new_end)))
            _maybe_check_pixel_values(custom_source.start_asset, new_end)

        solara.Markdown(msg("land_cover.start_asset"))
        AssetSelectComponent(
            types=["IMAGE"],
            value=_asset_value(custom_source.start_asset),
            on_value=_on_start_value,
            gee_interface=gee_interface,
        )
        solara.Markdown(msg("land_cover.end_asset"))
        AssetSelectComponent(
            types=["IMAGE"],
            value=_asset_value(custom_source.end_asset),
            on_value=_on_end_value,
            gee_interface=gee_interface,
        )

    # isinstance, not a truthiness guard: `water_mask` is `WaterMaskSpec | None`,
    # and the other two arms (`PixelValueMask`, `AssetBandMask`) have no
    # `.threshold` at all. Rendered only when the arm actually matches --
    # never a fabricated number for an arm this control cannot represent.
    if isinstance(current.water_mask, JrcSeasonalityMask):
        solara.SliderInt(
            label=msg("land_cover.water_mask"),
            value=current.water_mask.threshold,
            min=1,
            max=12,
            on_value=lambda v: spec.set(
                spec.value.evolve(water_mask=JrcSeasonalityMask(threshold=v))
            ),
        )
    elif current.water_mask is not None:
        solara.Markdown(msg("land_cover.water_mask_other_arm"))

    ProblemsAlert(step="land_cover", spec=spec.value)
