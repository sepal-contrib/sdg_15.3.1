"""Exports: one source per layer, into a single launcher.

The user picks what to export rather than exporting all seven at once, which is
what the legacy offered. Asset basenames come from ``sdg1531.naming`` so a
repeat run is named consistently and the collision suffix is applied once, in
the domain.

``vis_params`` is a single dict: all seven layers use the ``default``
visualization slot. Multi-slot exports arrive when pysepal widens the field to
accept a list; this app needs nothing from that change.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import solara
from pysepal.solara.components.export import (
    ExportLauncher,
    ExportSource,
    ResolvedExport,
)

from app.message import msg
from app.panels.map_layers import layer_vis_params
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import ClassifiedLayer, IndicatorMaps
from sdg1531.enums import IndicatorLayer
from sdg1531.naming import LAYER_BASENAMES

__all__ = ("ExportsPanel", "export_sources")

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
                label=layer.label,
                kind="image",
                resolve=make(),
            )
        )
    return tuple(sources)


@solara.component
def ExportsPanel(
    maps: solara.Reactive[IndicatorMaps | None],
    ctx: solara.Reactive[Any],
    spec: Any,
    gee_interface: Any,
) -> None:
    """``spec`` is accepted but unused, for the same reason ``MapLayersPanel``
    accepts an unused ``gee_interface``: ``page.py`` passes a uniform set of
    objects to every right-panel output section, and this panel needs nothing
    from the run spec -- asset basenames come from ``sdg1531.naming`` off the
    layer id alone.

    ``gee_interface`` IS used, and must be threaded through to
    ``ExportLauncher`` rather than left for its own internal
    ``get_current_gee_interface()`` fallback to resolve. Both
    ``pysepal``'s own reference integration
    (``demo_apps/solara_map_app/component/tile/export.py``) and
    ``sepal-gee-bundle``'s shipped ``tmf_sepal`` app
    (``apps/tmf_sepal/components/export_step.py``) resolve it once at the page
    level and pass it down for the same documented reason: ``MapApp``'s
    ``right_panel_content`` is a separate render root from the
    ``@with_sepal_sessions`` page that establishes the session, so a nested
    panel calling ``get_current_gee_interface()`` itself can raise
    ``SepalSessionError`` even though the page-level lookup succeeds.
    """
    # No `solara.Markdown(msg("exports.description"))` here: `page.py`'s section
    # dict already carries that same string as the right-panel section's own
    # `description`, which `MapApp` renders under the section title. Rendering
    # it a second time here duplicated the sentence on screen for the Layers
    # panel (Task 10); this panel drops it up front instead.
    if maps.value is None or ctx.value is None:
        solara.Markdown(msg("exports.build_first"))
        return

    ExportLauncher(
        sources=export_sources(maps.value, ctx.value),
        label=msg("exports.button"),
        button_text=True,
        block=True,
        gee_interface=gee_interface,
    )
