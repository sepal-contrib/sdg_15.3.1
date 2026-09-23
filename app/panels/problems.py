"""One styled component for the validation messages no control can carry.

Errors and warnings only -- never "3 selected" status lines -- grouped so
every error appears above every warning, because an error is the thing that
blocks and should not be read after the advice.

**This is now the fallback, not the main route.** A problem whose field
belongs to a control on screen is drawn by that control instead
(``app/panels/fields.py``), where it sits in the message line the input
already reserves rather than a scroll below it. What still arrives here is
what no control owns: ``climate.coefficient`` and ``periods.state`` have no
widget in any step, and ``app/steps/run.py``'s build refusal is a real error
with no ``Problem`` behind it at all. Every step ends by passing
``ProblemRouter.rest`` here, so a new rule in ``sdg1531.validate`` surfaces in
this alert rather than nowhere.
"""

from __future__ import annotations

import reacton.ipyvuetify as rv
import solara

from sdg1531.validate import Problem

__all__ = ("ProblemsList",)

#: `dense` + `text` is Vuetify's quietest alert: a tinted background in the
#: severity colour with no heavy border or elevation, which is the right weight
#: for a message that sits inline under a form control rather than interrupting
#: the page. `outlined` was measured against it in the browser and reads as a
#: second card boundary inside a section that already has one.
_ALERT_CLASS = "mb-2"


@solara.component
def ProblemsList(problems: tuple[Problem, ...] = ()) -> None:
    """Render an already-selected set of problems, grouped by severity.

    Renders nothing when there are none, so a step can call it
    unconditionally with whatever its router did not hand to a control.
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
