"""Form controls that carry their own validation messages.

A step used to render every one of its problems in one ``ProblemsAlert`` at
the bottom of the section. With four sections stacked in one 450px panel that
put the message a scroll away from the control that caused it: an empty
Sensors field reported "Select at least one sensor" below five other controls,
which the repo owner read as *"the error is to the bottom of that step... it is
difficult to see"*. Vuetify already has the right slot for this -- the message
line every input reserves under itself -- so the message goes there.

**Nothing is allowed to vanish on the way.** :class:`ProblemRouter` hands each
problem to exactly one control and keeps what no control claimed, so a step
ends with ``router.rest`` going to its alert. Adding a rule to
``sdg1531.validate`` whose field no control here knows about therefore makes
that message appear in the alert -- the old behaviour -- rather than nowhere.
``tests/app/test_fields.py`` pins that property directly.

Severity is split across two mechanisms because Vuetify 2 only has one:
``v-input`` takes ``error-messages`` (red, and it marks the field itself) but
has no warning equivalent, so a non-fatal problem is drawn by
:func:`FieldMessages` underneath instead. ``warning--text`` is a real class
here even though it appears nowhere in the shipped bundle: Vuetify 2 writes a
``<style id="vuetify-theme-stylesheet">`` at runtime holding
``.<colour>--text`` for every theme colour, and pysepal's ``setup_theme_colors``
sets ``warning``. That was checked in the bundle (``genStyles`` +
``checkOrCreateStyleElement``) rather than assumed -- see
``app/panels/section_header.py`` for what this app already paid for assuming a
CSS name resolved.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import reacton.ipyvuetify as rv
import solara

from app.state import owns
from sdg1531.validate import Problem

__all__ = (
    "FieldMessages",
    "ProblemRouter",
    "SelectField",
    "SliderField",
)

#: Vuetify's own ``.v-messages`` metrics, reproduced for the standalone
#: warning line so it sits exactly where an ``error-messages`` line would. The
#: negative top margin pulls it up over the empty message row the input above
#: already reserves; without it every warning adds a blank line of its own.
_MESSAGE_STYLE = "font-size: 12px; line-height: 14px; padding: 0 12px 6px; margin-top: -6px;"


class ProblemRouter:
    """Hands each problem to exactly one control, and keeps the leftovers.

    Order matters and is the caller's to get right: :meth:`take` is greedy
    over dotted subtrees, so ``land_cover.start_asset`` must be taken before
    ``land_cover``, which owns it. Getting that order wrong puts a message on
    a neighbouring control; it cannot lose one, because whatever no ``take``
    claimed is still in :attr:`rest`.
    """

    def __init__(self, problems: Sequence[Problem]) -> None:
        self._left = list(problems)

    def take(self, *fields: str) -> tuple[Problem, ...]:
        """Every remaining problem under one of ``fields``, removed from the pool."""
        taken: list[Problem] = []
        left: list[Problem] = []
        for problem in self._left:
            target = taken if any(owns(field, problem.field) for field in fields) else left
            target.append(problem)
        self._left = left
        return tuple(taken)

    @property
    def rest(self) -> tuple[Problem, ...]:
        """What no control claimed -- for the step's own alert."""
        return tuple(self._left)


def _split(problems: Sequence[Problem]) -> tuple[list[str], list[str]]:
    """``(blocking, advisory)`` message text, in the order the rules emitted it."""
    return (
        [p.message for p in problems if p.fatal],
        [p.message for p in problems if not p.fatal],
    )


@solara.component
def FieldMessages(problems: Sequence[Problem] = ()) -> None:
    """Validation messages for a control that cannot carry its own.

    pysepal's ``AssetSelectComponent`` and ``AoiView`` are whole components,
    not ``v-input``s this module can hand ``error-messages`` to, and a
    collapsed ``PeriodOverrideControl`` has no Select on screen at all while
    still being able to own a problem. All three get this instead.

    Renders nothing when there is nothing to say, so it is safe to call
    unconditionally next to any control.
    """
    errors, warnings = _split(problems)
    for text, colour in ((errors, "error--text"), (warnings, "warning--text")):
        for message in text:
            rv.Html(tag="div", class_=colour, style_=_MESSAGE_STYLE, children=[message])


def _input_kwargs(problems: Sequence[Problem]) -> dict[str, Any]:
    """The ``v-input`` props every field in this panel shares.

    ``error_count`` is set explicitly because Vuetify defaults it to 1 and
    silently renders only the first message -- two rules failing on one field
    would look like one.

    ``dense`` and ``hide_details="auto"`` are what make four sections fit a
    450px panel. A stock ``v-input`` is ~72px tall: the control, plus a
    message row it reserves whether or not it has a message. Measured in a
    browser, that reserved row was most of the space between two year Selects
    and most of the gap between one section and the next -- the margins
    between sections were never the size of the problem. ``"auto"``, not
    ``True``: the row still appears the moment a field has something to say,
    which is the whole of ``app/panels/fields.py``'s reason to exist.
    """
    errors, _ = _split(problems)
    return {
        "error_messages": errors,
        "error_count": max(1, len(errors)),
        "dense": True,
        "hide_details": "auto",
    }


def _advisory(problems: Sequence[Problem]) -> tuple[Problem, ...]:
    """The half :func:`_input_kwargs` does NOT draw.

    A control carrying its own ``error-messages`` must hand
    :func:`FieldMessages` only what is left, or every fatal problem renders
    twice -- once by Vuetify, once underneath it.
    """
    return tuple(problem for problem in problems if not problem.fatal)


@solara.component
def SelectField(
    label: str,
    value: Any,
    items: list[Any],
    on_value: Callable[[Any], None],
    problems: Sequence[Problem] = (),
    multiple: bool = False,
) -> None:
    """A ``solara.Select`` that can show its own validation messages.

    ``solara.Select``/``SelectMultiple`` take no ``error_messages`` -- their
    signature is label/values/value/on_value/dense/disabled/classes/style and
    nothing else -- so this drops to the ``rv.Select`` those two wrap anyway.
    The widget in the render tree is the same ``v.Select`` either way, which is
    what lets the step tests keep selecting controls by class.
    """
    rv.Select(
        label=label,
        v_model=value,
        on_v_model=on_value,
        items=items,
        multiple=multiple,
        **_input_kwargs(problems),
    )
    FieldMessages(problems=_advisory(problems))


@solara.component
def SliderField(
    label: str,
    value: float,
    on_value: Callable[[Any], None],
    # Vuetify's own prop names, shadowing two builtins: a trailing underscore
    # would not reach the widget, and this signature is only ever called by
    # keyword.
    min: float,
    max: float,
    step: float | None = None,
    problems: Sequence[Problem] = (),
) -> None:
    """A slider that can show its own validation messages.

    ``thumb_label`` is on because a slider with a message under it no longer
    has room for the value readout ``solara.SliderFloat`` puts beside it.
    """
    kwargs: dict[str, Any] = {"step": step} if step is not None else {}
    rv.Slider(
        label=label,
        v_model=value,
        on_v_model=on_value,
        min=min,
        max=max,
        thumb_label=True,
        **kwargs,
        **_input_kwargs(problems),
    )
    FieldMessages(problems=_advisory(problems))
