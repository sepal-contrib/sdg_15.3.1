"""Land cover configuration.

Owns: land_cover, transition_matrix, water_mask and the land-cover period.
``transition_matrix`` has no control here yet -- like ``climate`` in the
productivity step, it waits on a dedicated task.

The land_cover union is what keeps its two arms apart: an ``EsaCciSource`` has
no fields at all, while a ``CustomLandCoverSource`` needs a start and an end
asset before it is usable, so the source Select renders text inputs for those
only when the custom arm is chosen -- leaving it selectable but permanently
unsatisfiable would just move ``missing_custom_land_cover_asset`` from a
validate() problem into a dead end.

``water_mask`` is a three-arm union too (``JrcSeasonalityMask``,
``PixelValueMask``, ``AssetBandMask``), plus ``None`` for "not chosen yet".
Only the JRC arm has a control, matching how the productivity step's
``vi_source`` control only ever writes ``SensorSelection``.
"""

from __future__ import annotations

from dataclasses import replace

import solara

from app.message import msg
from app.state import problems_for
from sdg1531.spec import (
    CustomLandCoverSource,
    EsaCciSource,
    JrcSeasonalityMask,
    RunSpec,
)

__all__ = ("LandCoverStep",)

_SOURCE_KEYS = ("esa", "custom")


def _source_labels() -> dict[str, str]:
    """Map each land-cover source key to its translated display label.

    Rebuilt on every render, not cached: ``msg()`` subscribes to the current
    locale, so a cached copy would not update when the language changes.
    """
    return {key: msg(f"land_cover.{key}") for key in _SOURCE_KEYS}


@solara.component
def LandCoverStep(spec: solara.Reactive[RunSpec]) -> None:
    solara.Markdown(msg("land_cover.description"))

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

    if isinstance(current.land_cover, CustomLandCoverSource):
        custom_source = current.land_cover
        solara.InputText(
            label=msg("land_cover.start_asset"),
            value=custom_source.start_asset,
            continuous_update=True,
            on_value=lambda v: spec.set(
                spec.value.evolve(land_cover=replace(custom_source, start_asset=v))
            ),
        )
        solara.InputText(
            label=msg("land_cover.end_asset"),
            value=custom_source.end_asset,
            continuous_update=True,
            on_value=lambda v: spec.set(
                spec.value.evolve(land_cover=replace(custom_source, end_asset=v))
            ),
        )

    # isinstance, not a truthiness guard: `water_mask` is `WaterMaskSpec | None`,
    # and the other two arms (`PixelValueMask`, `AssetBandMask`) have no
    # `.threshold` at all.
    threshold = (
        current.water_mask.threshold if isinstance(current.water_mask, JrcSeasonalityMask) else 6
    )
    solara.SliderInt(
        label=msg("land_cover.water_mask"),
        value=threshold,
        min=1,
        max=12,
        on_value=lambda v: spec.set(spec.value.evolve(water_mask=JrcSeasonalityMask(threshold=v))),
    )

    for problem in problems_for("land_cover", spec.value):
        solara.Markdown(f"**{problem.message}**" if problem.fatal else problem.message)
