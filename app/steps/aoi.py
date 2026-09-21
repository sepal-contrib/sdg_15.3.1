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

    # Deliberately no "Selected: {name}" and no `ProblemsAlert`: `AoiView`
    # already shows the selection, and this step's one rule (`missing_aoi`)
    # says "Select an area of interest" under a heading that says the same.
    # Its real consequence is drawn by the tab strip instead -- PARAMS and
    # Results lock until an AOI exists (`app/tabs.py`'s `_tab_state`).
    #
    # Safe ONLY while `missing_aoi` is the step's only rule; a second would
    # have nowhere to appear. Pinned by `test_step_aoi.py`.
