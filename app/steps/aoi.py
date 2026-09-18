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

    # No "Selected: {name}" line here, and no `ProblemsAlert` either.
    #
    # `AoiView`'s own controls already show the current selection, so the
    # first restated what was on screen two rows above it -- the repo owner's
    # own example of the noise this panel should not carry ("in the AOI
    # section remove the 'SELECTED...' that is useless").
    #
    # The alert went for the same reason, one request later: this step owns
    # exactly ONE validation rule, `missing_aoi`, whose message is "Select an
    # area of interest" -- shown on the tab whose entire content is the area
    # picker, under a heading that already says "Choose the area the indicator
    # is computed over". What it was really reporting is the CONSEQUENCE, and
    # since the owner asked for PARAMS to be deactivated until an AOI exists
    # ("if the AOI is not set, PARAMS should be deactivated, and therefore,
    # the 'select an AOI' should be deactivated"), the tab strip now shows
    # that consequence directly: two visibly locked tabs, at the moment it
    # matters. See `app/tabs.py`'s `_tab_state`.
    #
    # This is safe only while `missing_aoi` really is the step's only rule --
    # a second AOI rule would silently have nowhere to appear. Pinned by
    # `tests/app/test_step_aoi.py::test_the_aoi_step_still_owns_exactly_the_
    # one_rule_its_missing_alert_assumes`, which fails loudly if the domain
    # ever grows one.
