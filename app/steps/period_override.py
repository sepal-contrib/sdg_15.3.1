"""A single override toggle, shared by the SOC and land-cover steps.

Both own an optional ``PeriodOverride`` that inherits from ``periods.overall``
when unset (``PeriodOverride.resolve``). Two equal-looking year Selects for
what is really ONE required window plus TWO optional narrowings made the app
look like it wanted three answers, so each override hides behind a checkbox,
off by default, showing the inherited window instead.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import reacton.ipyvuetify as rv
import solara

from app.message import msg
from app.panels.fields import FieldMessages, ProblemRouter, SelectField
from sdg1531.spec import Period, PeriodOverride
from sdg1531.validate import Problem

__all__ = ("PeriodOverrideControl",)


def _fmt(year: int | None) -> str:
    """A still-unknown bound (``periods.overall`` not set yet -- the Run step
    comes AFTER both Soc and Land cover in tab order, so this is the common
    first-visit case, not an edge case) reads as ``"?"`` rather than the
    Python ``None`` or an invented year."""
    return str(year) if year is not None else "?"


@solara.component
def PeriodOverrideControl(
    override: PeriodOverride,
    overall: Period,
    years: list[int],
    start_label: str,
    end_label: str,
    on_change: Callable[[PeriodOverride], None],
    field: str = "",
    problems: Sequence[Problem] = (),
) -> None:
    """Collapsed (showing the inherited window as plain text) unless
    ``override`` already holds a value on mount -- a spec loaded with a real
    override must not hide that fact behind an unchecked box the user has no
    reason to tick.

    ``rv.Checkbox``, not ``solara.Checkbox``: the latter has no return-type
    annotation in solara's own stubs, the same reason ``app/tabs.py`` avoids
    ``solara.Row``/``Button`` (see that module's own comments) -- ``mypy
    --strict`` refuses to call an unannotated component factory.

    ``field`` is the caller's own dotted spec path (``periods.soc``,
    ``periods.land_cover``) and is what lets one shared control route
    ``problems`` onto the right Select without knowing which step it serves.
    **Both severities still show while the override is collapsed**: a rule
    like ``soc_start_before_cci`` reads the window this period RESOLVES to, so
    it can fire against the inherited years when there is no Select on screen
    to hang it on -- hence the unconditional :func:`FieldMessages` on that
    branch rather than a message tied to a control that is not there.
    """
    enabled, set_enabled = solara.use_state(bool(override.start or override.end))

    def _toggle(value: bool) -> None:
        set_enabled(value)
        if not value:
            # The trap the brief names directly: switching the override back
            # off must CLEAR it, or the spec keeps computing the stale years
            # while the UI claims "inherited" -- the silently-wrong-data
            # failure class this project has spent the most effort
            # eliminating.
            on_change(PeriodOverride(None, None))

    rv.Checkbox(label=msg("period_override.toggle"), v_model=enabled, on_v_model=_toggle)

    if enabled:
        router = ProblemRouter(problems)
        # Same "no invented default" rule the two Selects always had (see
        # `soc.py`'s own long-standing comment on this): `value=override.start`
        # verbatim, never `or <some year>` -- an unset bound is correct, and a
        # fabricated one would misstate the window the run actually uses.
        SelectField(
            label=start_label,
            value=override.start,
            items=years,
            on_value=lambda v: on_change(PeriodOverride(v, override.end)),
            problems=router.take(f"{field}.start"),
        )
        SelectField(
            label=end_label,
            value=override.end,
            items=years,
            on_value=lambda v: on_change(PeriodOverride(override.start, v)),
            problems=router.take(f"{field}.end"),
        )
        # `soc_period_collapses` and `land_cover_period_collapses` are emitted
        # on the period itself, not on either endpoint: the window is what is
        # wrong, and neither year alone is the thing to correct.
        FieldMessages(problems=router.rest)
    else:
        resolved = override.resolve(overall)
        solara.Markdown(
            msg("period_override.inherited", start=_fmt(resolved.start), end=_fmt(resolved.end))
        )
        FieldMessages(problems=problems)
