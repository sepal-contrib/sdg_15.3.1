"""The land-cover transition matrix, as an editable grid.

Which (from, to) land-cover transitions count as degradation, stable or
improvement. The legacy had a widget for this; the port deleted it with the
rest of ``component/widget/`` and the replacement was never written, so every
run has used the default IPCC matrix since. The domain was ready the whole
time -- ``TransitionMatrix`` carries ``with_cell``, ``to_list``, ``from_list``
and ``is_default``, and ``validate()`` has ``invalid_transition_matrix``.

**The widget owns no state.** Vue writes a whole grid back to the ``matrix``
trait, this module turns it into a frozen ``TransitionMatrix``, and the caller
puts that on the spec. Nothing is edited in place: the legacy's
``widget/transition_matrix.py:46`` index-assigned into a module-level
constant, which under Solara leaked one user's matrix into every other session
in the worker, and that is the specific bug the frozen domain type exists to
make unrepresentable.

The template is adapted from ``sepal_mgci``'s own matrix widget; see the
comment block in ``vue/transition_matrix.vue`` for the three defects that were
fixed on the way across.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

import ipyvuetify as v
import reacton.ipyvuetify as rv
import solara
from traitlets import Bool, Dict, List, Unicode

from app.message import msg
from app.panels.fields import FieldMessages
from sdg1531.scheme import TransitionMatrix
from sdg1531.validate import Problem

__all__ = ("CELL_VALUES", "TransitionMatrixField", "TransitionMatrixInput", "decode_table")

#: The vocabulary a cell may hold, in the order the dropdown offers it.
#: ``sdg1531.validate`` rejects anything outside this set
#: (``invalid_transition_matrix``), so the control cannot offer more.
CELL_VALUES = (-1, 0, 1)

#: Cell colours, keyed by value. Not from a Vuetify theme class: these are
#: painted as an inline ``background-color`` on a table cell, where a
#: ``--text`` helper class does not apply. Low-alpha so the value stays
#: readable on either theme rather than fighting the text colour. Proxied
#: because this module is the one that exists BECAUSE a shared mutable table
#: leaked between sessions -- see the module docstring.
_CELL_COLORS: Mapping[int, str] = MappingProxyType(
    {
        -1: "rgba(255, 82, 82, 0.28)",
        0: "rgba(158, 158, 158, 0.20)",
        1: "rgba(76, 175, 80, 0.28)",
    }
)


def decode_table() -> dict[int, dict[str, str]]:
    """What each cell value means, for the dropdown and the cell colour.

    Rebuilt per call rather than cached: ``msg()`` subscribes to the current
    locale, so a cached copy would keep the language it was first built in
    (the same reason ``app/steps/productivity.py`` rebuilds its own label
    tables).
    """
    return {
        value: {
            "abrv": str(msg(f"matrix.value.{name}.abrv")),
            "label": str(msg(f"matrix.value.{name}.label")),
            "color": _CELL_COLORS[value],
        }
        for value, name in zip(CELL_VALUES, ("degradation", "stable", "improvement"), strict=True)
    }


class TransitionMatrixInput(v.VuetifyTemplate):
    """The Vue transport: an N x N grid of value pickers.

    ``matrix`` is two-way -- Vue writes the whole grid back to it on a cell
    change or a reset, which is what :func:`TransitionMatrixField` observes.
    There are no ``vue_*`` handler methods: a synced trait is what reacton can
    actually subscribe to, and an event callback would need the widget
    instance, which a component rendering through ``.element()`` does not hold.
    """

    template_file = Unicode(str(Path(__file__).parent / "vue" / "transition_matrix.vue")).tag(
        sync=True
    )

    class_names = List(Unicode(), default_value=[]).tag(sync=True)
    matrix = List(List(), default_value=[]).tag(sync=True)
    default_matrix = List(List(), default_value=[]).tag(sync=True)
    decode = Dict(default_value={}).tag(sync=True)
    disabled = Bool(False).tag(sync=True)
    reset_label = Unicode("").tag(sync=True)
    from_label = Unicode("").tag(sync=True)
    to_label = Unicode("").tag(sync=True)
    cycle_label = Unicode("").tag(sync=True)


@solara.component
def TransitionMatrixField(
    value: TransitionMatrix,
    on_value: Callable[[TransitionMatrix], None],
    class_names: Sequence[str],
    problems: Sequence[Problem] = (),
    disabled: bool = False,
) -> None:
    """The matrix editor, wired to a frozen ``TransitionMatrix``.

    ``on_value`` receives a NEW matrix; this never mutates the one passed in.
    ``class_names`` comes from the caller rather than being read from
    ``sdg1531.tables`` here, because a custom land-cover source can bring its
    own class list and the grid has to follow it.
    """

    def _on_grid(rows: Any) -> None:
        # Vue hands back a plain list of lists. `from_list` is what makes it a
        # frozen matrix again, and it is also the only place ints are coerced
        # -- a select can return its value as a string.
        new = TransitionMatrix.from_list(rows)
        if new != value:
            on_value(new)

    decode = decode_table()
    # `str` keys: a Dict trait carrying int keys reaches Vue as JSON, where
    # object keys are strings either way. Spelling it here keeps the template
    # from having to guess which it got.
    TransitionMatrixInput.element(
        class_names=list(class_names),
        matrix=value.to_list(),
        default_matrix=TransitionMatrix.default().to_list(),
        decode={str(k): v for k, v in decode.items()},
        disabled=disabled,
        reset_label=msg("matrix.reset"),
        from_label=msg("matrix.from"),
        to_label=msg("matrix.to"),
        cycle_label=msg("matrix.cycle"),
        on_matrix=_on_grid,
    )

    # A legend for the three values. The cells show the abbreviation only --
    # at 7x7 in a 450px panel there is no room for a word -- so the mapping
    # has to be written down somewhere, and a tooltip per cell is not it.
    with rv.Html(tag="div", class_="d-flex flex-wrap justify-center mt-1", style_="gap: 12px;"):
        for entry in decode.values():
            with rv.Html(tag="div", class_="d-flex align-center", style_="gap: 4px;"):
                rv.Html(
                    tag="span",
                    style_=(
                        f"background-color: {entry['color']}; width: 14px; height: 14px; "
                        "display: inline-block; border-radius: 2px;"
                    ),
                    children=[],
                )
                rv.Html(
                    tag="span",
                    class_="caption text--secondary",
                    children=[f"{entry['abrv']} — {entry['label']}"],
                )

    # Underneath the grid, not a subtitle above it: the section header already
    # names what this step is, and a second heading inside it read as a
    # sub-panel. The prose explains a control the reader has just looked at.
    rv.Html(
        tag="p",
        class_="caption text--secondary mt-1 mb-0",
        children=[msg("matrix.description")],
    )

    FieldMessages(problems=problems)
