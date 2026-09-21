"""Exports: one source per layer.

The user picks what to export rather than exporting all seven at once, which
is what the legacy offered. Asset basenames come from ``sdg1531.naming`` so a
repeat run is named consistently and the collision suffix is applied once, in
the domain.

``vis_params`` is a single dict: all seven layers use the ``default``
visualization slot.

**This module renders nothing.** ``app/panels/map_layers.py`` hosts the dialog
and gives each row its own export icon; what is left here is the sources.
"""

from __future__ import annotations

from collections.abc import Callable

from pysepal.solara.components.export import ExportSource, ResolvedExport

from app.panels.layer_style import layer_name, layer_vis_params
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import ClassifiedLayer, IndicatorMaps
from sdg1531.enums import IndicatorLayer
from sdg1531.naming import LAYER_BASENAMES

__all__ = ("export_sources",)

#: What the legacy passed as maxPixels (gdrive.py:168). Carried so a large AOI
#: fails the same way it used to rather than at a different threshold.
_MAX_PIXELS = int(1e13)


def export_sources(maps: IndicatorMaps, ctx: ExecutionContext) -> tuple[ExportSource, ...]:
    """One ExportSource per layer.

    ``resolve`` is a 0-arg callable invoked when the user presses Export, so the
    band selection and the region are read at press time rather than at render.

    The clip, region, scale and maxPixels all transcribe the legacy's export task
    config (``component/scripts/gdrive.py:160-170``). None of them is optional in
    practice: ``ResolvedExport`` defaults ``region`` and ``default_scale`` to
    ``None``, which would export an unbounded footprint at a default scale instead
    of the AOI at the user's analysis scale. ``analysis_scale`` is the right scale
    because the legacy took the export scale from the first sensor
    (``run_15_3_1.py:34``) and ``resolve()`` computes ``analysis_scale`` the same
    way (``resolve.py:274``).
    """
    sources = []
    for layer_id, layer in maps.layers().items():

        def make(
            layer: ClassifiedLayer = layer, layer_id: IndicatorLayer = layer_id
        ) -> Callable[[], ResolvedExport]:
            def resolve() -> ResolvedExport:
                return ResolvedExport(
                    # .clip(feature_collection), not .clip(geometry): gdrive.py:161
                    ee_object=layer.image.select(layer.band).clip(ctx.feature_collection),
                    default_name=LAYER_BASENAMES[layer_id.value],
                    region=ctx.geometry,
                    default_scale=maps.resolved.analysis_scale,
                    max_pixels=_MAX_PIXELS,
                    vis_params=layer_vis_params(layer_id),
                )

            return resolve

        sources.append(
            ExportSource(
                id=layer_id.value,
                # Not `layer.label`: that is the domain's raw snake id
                # (`ClassifiedLayer.label` docstring; frozen under decision
                # D9), and this is the label the user picks the export by
                # (final-review finding M1).
                label=layer_name(layer_id),
                kind="image",
                resolve=make(),
            )
        )
    return tuple(sources)
