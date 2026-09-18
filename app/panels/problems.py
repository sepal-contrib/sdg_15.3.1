"""One styled component for every validation message the app reports.

Replaces ``app.state.render_problems``, which emitted one bare
``solara.Markdown`` per problem -- bolded when fatal, plain otherwise. The repo
owner's objection was to exactly that: *"the parameters I believe should use a
single component for reporting the errors? a single component that shows the
validation errors, and with a proper styling, I don't like that plain
markdown"*.

**Kept where it is, not consolidated into one panel-wide list.** The owner
weighed both -- *"I don't know if we should have them separate ... because is
nice to have the feedback immediately"* -- and immediacy is the reason a
message sits next to the control that causes it. So this is ONE component used
in several places, not one place showing everything: each step still renders
its own ``ProblemsAlert(step, spec)`` at the end of its body, exactly where
``render_problems`` used to be called.

**Errors and warnings only.** The other half of the same request: *"at least it
should only report errors/warnings, not useless info like ('x selected')"*.
Informational lines that were being rendered through the same channel are gone
-- ``aoi.selected`` ("Selected: {name}"), which restated what ``AoiView``'s own
control already shows, and ``run.ready``/``run.blocked``, which restated what
the Results tab's own enabled/disabled state already says. What survives is a
real field hint (the sensor-coverage line under the year selects), and it is
deliberately NOT routed through here -- see ``app/steps/run.py``.

Severity is ``Problem.fatal``, never a second notion of it: fatal problems are
what ``is_runnable`` blocks on, so they are errors, and everything else is a
warning. The two are grouped rather than interleaved so a user reading a
section sees what BLOCKS them before what merely warns them.
"""

from __future__ import annotations

import reacton.ipyvuetify as rv
import solara

from app.state import problems_for
from sdg1531.spec import RunSpec
from sdg1531.validate import Problem

__all__ = ("ProblemsAlert", "ProblemsList")

#: `dense` + `text` is Vuetify's quietest alert: a tinted background in the
#: severity colour with no heavy border or elevation, which is the right weight
#: for a message that sits inline under a form control rather than interrupting
#: the page. `outlined` was measured against it in the browser and reads as a
#: second card boundary inside a section that already has one.
_ALERT_CLASS = "mb-2"


@solara.component
def ProblemsList(problems: tuple[Problem, ...]) -> None:
    """Render an already-selected set of problems, grouped by severity.

    Split from :func:`ProblemsAlert` so a caller holding problems that did NOT
    come from ``problems_for`` -- ``app/steps/run.py``'s build refusal, which
    is a real error with no ``Problem`` behind it -- gets the identical styling
    instead of falling back to its own bold ``solara.Markdown``.
    """
    fatal = [problem for problem in problems if problem.fatal]
    warnings = [problem for problem in problems if not problem.fatal]

    for severity, group in (("error", fatal), ("warning", warnings)):
        if not group:
            continue
        with rv.Alert(type=severity, dense=True, text=True, class_=_ALERT_CLASS):
            # One <div> per message, not a bullet list: a single problem is the
            # common case, and a one-item <ul> reads as a formatting accident.
            for problem in group:
                rv.Html(tag="div", children=[problem.message])


@solara.component
def ProblemsAlert(step: str, spec: RunSpec) -> None:
    """Every problem ``step`` owns, styled. Renders nothing when there are none.

    A ``@solara.component``, unlike the plain function it replaces: it mounts
    ``rv.Alert`` widgets of its own, so it wants its own reconciliation
    identity rather than splicing widgets into whichever caller happens to
    invoke it.
    """
    ProblemsList(problems=problems_for(step, spec))
