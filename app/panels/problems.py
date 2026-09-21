"""One styled component for every validation message the app reports.

Errors and warnings only -- never "3 selected" status lines -- grouped so
every error appears above every warning, because an error is the thing that
blocks and should not be read after the advice.

**Kept per-section, not consolidated into one panel-wide list**: a message
next to the control that caused it is read while the user is still looking at
that control. What was wrong before was the STYLING (bare markdown), not the
placement.
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
