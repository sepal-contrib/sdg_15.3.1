"""How one computed layer is named, coloured, and drawn.

Three functions, and everything that shows a layer reads them rather than
deriving its own: ``app/panels/map_layers.py`` draws the map tiles,
``app/panels/legend.py`` colours the floating legend, and
``app/panels/exports.py`` stamps the vis params onto the exported asset. That
is the point of the module -- the legend agrees with the tiles by construction
instead of by two tables that happen to line up today.

It exists as its own module because the alternative is a cycle: the layers
panel now hosts the export dialog (a row's own export icon, see that module's
docstring), so it imports ``export_sources`` from ``app/panels/exports.py``,
which needs the name and the vis params. These three lived in
``map_layers.py`` until that edge appeared.

Nothing here decides which layers exist -- that is ``IndicatorMaps.layers()``
-- and nothing here touches the domain's graphs: ``display_image`` builds a
display-only derivative, and decision D9 keeps the graphs under it frozen.
"""

from __future__ import annotations

from typing import Any, cast

import ee

from app.message import msg
from sdg1531.engine.indicator import ClassifiedLayer
from sdg1531.enums import IndicatorLayer
from sdg1531.tables import DEGRADATION_COLORS

__all__ = ("display_image", "layer_name", "layer_vis_params")


def layer_vis_params(layer_id: IndicatorLayer) -> dict[str, Any]:
    """SEPAL-convention visualization for one layer.

    ``[1:]`` drops the NoData entry: the legacy viz is min=1..max=3 over the
    three classified colours, and index 0 is the unclassified background.
    """
    colours = list(DEGRADATION_COLORS.values())
    if layer_id is IndicatorLayer.PRODUCTIVITY_PERFORMANCE:
        return {"min": 1, "max": 2, "palette": colours[1:3]}
    return {"min": 1, "max": 3, "palette": colours[1:]}


def layer_name(layer_id: IndicatorLayer) -> str:
    """Translated display name for one layer.

    ``ClassifiedLayer.label`` is ``id.value`` -- a stable snake id, not a
    display string. The catalogue key is named after that same value, so
    every ``IndicatorLayer`` member resolves through it with no separate,
    hand-typed id-to-name mapping to keep in sync with the enum.
    """
    return str(msg(f"layers.names.{layer_id.value}"))


def display_image(layer: ClassifiedLayer, region: ee.Geometry) -> ee.Image:
    """The image actually drawn on the map for one layer: its classified band,
    clipped to the AOI and self-masked.

    ``selfMask()`` is not redundant with ``clip()`` and neither is redundant
    with the other. ``clip`` bounds the footprint but leaves every in-AOI
    pixel the classification left at 0 painted in the palette's FIRST colour,
    because the vis window starts at 1 and Earth Engine clamps anything at or
    below ``min`` to the min colour; ``selfMask`` drops those zeros but, on
    its own, leaves the rest of the world drawn wherever the source image is
    unbounded. Applying only one of the two is what put a globe-covering
    "Degraded" red under the AOI (``app/panels/map_layers.py``'s docstring
    records the report). The legacy applied both, in this order
    (``component/scripts/run_15_3_1.py:128``).

    DISPLAY ONLY. The domain graphs are untouched (decision D9) and the export
    path builds its own ``.clip(ctx.feature_collection)`` image
    (``app/panels/exports.py``), so nothing this returns reaches the parity
    harness.
    """
    # `ee`'s own stubs type `Image.selfMask()` loosely enough that mypy sees
    # `Any` here; the cast states the contract this module actually keeps.
    return cast("ee.Image", layer.image.select(layer.band).clip(region).selfMask())
