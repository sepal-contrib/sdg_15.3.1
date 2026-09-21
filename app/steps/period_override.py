"""A single override toggle, shared by the SOC and land-cover steps.

Both own an optional ``PeriodOverride`` that inherits from ``periods.overall``
when unset (``PeriodOverride.resolve``). Two equal-looking year Selects for
what is really ONE required window plus TWO optional narrowings made the app
look like it wanted three answers, so each override hides behind a checkbox,
off by default, showing the inherited window instead.
"""

from __future__ import annotations

from collections.abc import Callable

import reacton.ipyvuetify as rv
import solara

from app.message import msg
from sdg1531.spec import Period, PeriodOverride

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
) -> None:
    """Collapsed (showing the inherited window as plain text) unless
    ``override`` already holds a value on mount -- a spec loaded with a real
    override must not hide that fact behind an unchecked box the user has no
    reason to tick.

    ``rv.Checkbox``, not ``solara.Checkbox``: the latter has no return-type
    annotation in solara's own stubs, the same reason ``app/tabs.py`` avoids
    ``solara.Row``/``Button`` (see that module's own comments) -- ``mypy
    --strict`` refuses to call an unannotated component factory.
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
        # Same "no invented default" rule the two Selects always had (see
        # `soc.py`'s own long-standing comment on this): `value=override.start`
        # verbatim, never `or <some year>` -- an unset bound is correct, and a
        # fabricated one would misstate the window the run actually uses.
        solara.Select(
            label=start_label,
            value=override.start,
            values=years,
            on_value=lambda v: on_change(PeriodOverride(v, override.end)),
        )
        solara.Select(
            label=end_label,
            value=override.end,
            values=years,
            on_value=lambda v: on_change(PeriodOverride(override.start, v)),
        )
    else:
        resolved = override.resolve(overall)
        solara.Markdown(
            msg("period_override.inherited", start=_fmt(resolved.start), end=_fmt(resolved.end))
        )
