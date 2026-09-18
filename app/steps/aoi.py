"""Area of interest.

Writes ``RunSpec.aoi``. SHAPE and POINTS are excluded: both read paths that are
local to the server, which do not exist in a SEPAL container.
"""

from __future__ import annotations

from typing import Any, cast

import solara
from pysepal.solara.components.aoi import AoiView
from pysepal.solara.components.aoi.aoi_result import AoiResult

from app.adapters import to_domain_aoi
from app.message import msg
from app.panels.problems import ProblemsAlert
from sdg1531.spec import RunSpec

__all__ = ("AoiStep", "apply_selection")


def apply_selection(spec: solara.Reactive[RunSpec], selection: AoiResult | None) -> None:
    """Put the chosen AOI on the spec, leaving every other field alone.

    Split out of the component so it can be tested without a render tree.
    """
    spec.value = spec.value.evolve(aoi=to_domain_aoi(selection))


@solara.component
def AoiStep(spec: solara.Reactive[RunSpec], map_: Any) -> None:
    aoi_selection = solara.use_reactive(cast("AoiResult | None", None))
    aoi_loading = solara.use_reactive(False)

    def on_selection(value: AoiResult | None) -> None:
        apply_selection(spec, value)

    solara.Markdown(msg("aoi.description"))

    AoiView(
        value=aoi_selection,
        on_value=on_selection,
        loading=aoi_loading,
        # SHAPE and POINTS read server-local paths that a container does not have.
        methods=["-SHAPE", "-POINTS"],
        map_=map_,
        gee=True,
    )

    # No "Selected: {name}" line here any more. `AoiView`'s own controls
    # already show the current selection, so it restated what was on screen
    # two rows above it -- the repo owner's own example of the noise this
    # panel should not carry ("in the AOI section remove the 'SELECTED...'
    # that is useless"). `app/panels/problems.py` records the rule.
    ProblemsAlert(step="aoi", spec=spec.value)
