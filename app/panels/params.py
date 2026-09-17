"""The four configuration steps after AOI, as one tab's flat, headed sections.

The repo owner asked for this straight after the outputs tab got the same
treatment: *"I now think we could have just three tabs, AOI, PARAMS, Result"*
... *"in params, we should have sections, as you just did in the results."*
This module is ``app/panels/outputs.py`` for the OTHER four configuration
tabs (Assessment period, Productivity, Land cover, SOC) -- same shape, same
``SectionHeader``, same "no accordion" flatness -- read that module's
docstring first; this one only records what differs.

**Section order is the tab order these four steps already had, and is not
arbitrary.** Task 28 moved the step long called "Run" (routing key ``"run"``,
catalogue title "Assessment period") to be the FIRST of the five configuration
tabs, ahead of Productivity, Land cover and SOC, because
``app/steps/period_override.py``'s shared control shows the Land cover and SOC
steps the window they *inherit* from this step's own ``periods.overall`` --
that has to already be chosen, or the "inherited window" text they show is
empty or misleading. Folding four tabs into four SECTIONS does not relax that
dependency: Assessment period stays first here for the identical reason.
Productivity, Land cover and SOC keep the relative order they already had.

**Each section's own ``msg("<step>.description")`` now lives in its
``SectionHeader``,** not inside the step component itself -- the exact move
task 28 made for the five output panels (see that module's docstring for why
duplicating the description inside AND above a section reads as "a heading
followed by a stray sentence"). ``run.py``, ``productivity.py``,
``land_cover.py`` and ``soc.py`` no longer render their own description.

**Each section's own problems are still visible inside the tab**: this module
adds no new rendering for them because it does not need to -- every one of the
four step components already ends its own render body with
``app.state.render_problems(<step>, spec.value)`` (unchanged by this task),
so opening PARAMS and looking at, say, the Land cover section shows exactly
the problems ``problems_for("land_cover", ...)`` reports, same as when it was
its own tab. The single PARAMS chip in ``app/tabs.py``'s segment strip is a
SUMMARY across all four steps (see that module's ``_tab_state`` for the
combining rule), not a replacement for this per-section detail.

No chart lives in any of these four sections, so none of the chart-mount
trap ``app/panels/outputs.py`` documents applies here -- nothing in this
module needs an ``is_active``/``is_open`` gate.

Reuses ``app.panels.outputs``'s own ``SectionDescriptor`` rather than defining
a second, identical dataclass: the two modules' sections are the same shape
(title, icon, description, content, in DISPLAY order with no ``id``), so a
second definition would only be a name away from the first with nothing new
to say.
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
