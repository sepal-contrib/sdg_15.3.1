"""The four configuration steps after AOI, as one tab's flat, headed sections.

The same shape as ``app/panels/outputs.py`` -- same ``SectionHeader``, same
flatness, no accordion -- for the configuration steps instead of the outputs.

**Section order is not arbitrary.** The assessment period comes first because
``app/steps/period_override.py`` shows Land cover and SOC inheriting it, so it
has to be chosen before them; Productivity sits between. Order lives in list
position alone.
"""

from __future__ import annotations

from typing import Any

import reacton.ipyvuetify as rv
import solara

from app.message import msg
from app.panels.outputs import SectionDescriptor
from app.panels.section_header import SectionHeader
from app.steps.land_cover import LandCoverStep
from app.steps.productivity import ProductivityStep
from app.steps.run import BuildOutcome, RunStep
from app.steps.soc import SocStep
from sdg1531.spec import RunSpec

__all__ = ("ParamsPanel", "param_sections")


def param_sections(
    spec: solara.Reactive[RunSpec] | None = None,
    outcome: BuildOutcome | None = None,
    gee_interface: Any = None,
) -> list[SectionDescriptor]:
    """The four sections, in DISPLAY order: Assessment period -> Productivity
    -> Land cover -> SOC. Bare-callable with every argument defaulting to
    ``None`` -- same reason ``app.tabs.workflow_tabs`` and
    ``app.panels.outputs.output_sections`` are; see ``workflow_tabs``'s own
    docstring for the mechanism (an inert element descriptor, never a step's
    render body, is what a bare call like ``param_sections()`` builds).

    ``run_content`` is the one section guarded on BOTH ``spec`` and
    ``outcome`` -- ``RunStep`` takes a bare ``BuildOutcome``, unlike the other
    three steps' already-``X | None`` arguments -- the same mypy-narrowing
    reason ``workflow_tabs`` guards its own ``RunStep``/``OutputsPanel``
    calls today.
    """
    run_content: list[object] = (
        [RunStep(spec=spec, outcome=outcome)] if spec is not None and outcome is not None else []
    )
    productivity_content: list[object] = [ProductivityStep(spec=spec)] if spec is not None else []
    # No `gee_interface is not None` guard: `LandCoverStep`'s own parameter
    # already defaults to `None` (see `app.tabs.workflow_tabs`'s identical
    # comment on the same call), so there is no bare `Reactive[...]` here for
    # mypy to narrow.
    land_cover_content: list[object] = (
        [LandCoverStep(spec=spec, gee_interface=gee_interface)] if spec is not None else []
    )
    soc_content: list[object] = [SocStep(spec=spec)] if spec is not None else []

    return [
        SectionDescriptor(
            msg("step.run"), "mdi-calendar-range", msg("run.description"), run_content
        ),
        SectionDescriptor(
            msg("step.productivity"),
            "mdi-sprout-outline",
            msg("productivity.description"),
            productivity_content,
        ),
        SectionDescriptor(
            msg("step.land_cover"),
            "mdi-terrain",
            msg("land_cover.description"),
            land_cover_content,
        ),
        SectionDescriptor(
            msg("step.soc"), "mdi-layers-outline", msg("soc.description"), soc_content
        ),
    ]


@solara.component
def ParamsPanel(
    spec: solara.Reactive[RunSpec],
    outcome: BuildOutcome,
    gee_interface: Any = None,
) -> None:
    """The PARAMS tab's whole content: four flat, headed sections over
    ``param_sections()``, stacked and always visible -- identical structure to
    ``app.panels.outputs.OutputsPanel``, just over a different four sections.
    """
    sections = param_sections(spec=spec, outcome=outcome, gee_interface=gee_interface)

    for section in sections:
        SectionHeader(title=section.title, icon=section.icon, description=section.description)
        # A plain, unstyled `rv.Html` div -- see `OutputsPanel`'s identical
        # comment on the same construction for why this introduces no CSS
        # visibility toggle of its own.
        rv.Html(tag="div", style_="margin-bottom: 16px;", children=section.content)
