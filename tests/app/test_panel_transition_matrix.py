"""``app/panels/transition_matrix.py``: the matrix editor and its template.

The widget is adapted from ``sepal_mgci``'s, and two of the three departures
from that original are defects it still carries. Both are pinned here, because
both are invisible to a Python-side test of the kind that repo has: the
template is never rendered there, so a script block that registers nothing and
a falsy-zero comparison both pass.

The third property is the one the domain cares about: editing a cell produces
a NEW matrix. The legacy widget index-assigned into a module-level constant,
which under Solara leaked one user's matrix into every session in the worker.
"""

from __future__ import annotations

import re
from pathlib import Path

import ipyvuetify as v
import pytest
import solara

from app.message import msg
from app.panels.transition_matrix import (
    CELL_VALUES,
    TransitionMatrixField,
    TransitionMatrixInput,
    decode_table,
)
from sdg1531.scheme import TransitionMatrix
from sdg1531.tables import DEFAULT_LC_CLASS_NAMES
from tests.app.render_helpers import find_widget

_TEMPLATE = Path(TransitionMatrixInput.template_file.default_value)

#: A `<script>` block with its comments removed.
#:
#: The checks below look for spellings that must NOT appear, and this file's own
#: header comment names every one of them -- it documents the mgci defects it was
#: adapted away from. Grepping the raw text would therefore match the prose
#: describing a bug and report the bug itself, which is the same trap
#: ``tests/app/test_icons.py`` reads icon names by AST to avoid.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)


def _script() -> str:
    source = _TEMPLATE.read_text()
    body = source[source.index("<script>") : source.index("</script>")]
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", body))


def _render(matrix: TransitionMatrix, captured: list[TransitionMatrix]) -> object:
    box, rc = solara.render(
        TransitionMatrixField(
            value=matrix,
            on_value=captured.append,
            class_names=DEFAULT_LC_CLASS_NAMES,
        ),
        handle_error=False,
    )
    assert rc is not None
    return box


# ---------------------------------------------------------------------------
# The template itself.
# ---------------------------------------------------------------------------


def test_the_template_registers_its_component() -> None:
    """``module.exports``, and neither of the two spellings that do not work.

    Measured in a browser, because none of it is visible from Python:

    * ``modules.export`` (mgci's) registers nothing at all -- the template
      then renders against undefined state.
    * ``export default`` is a hard ``SyntaxError: Unexpected token 'export'``
      here. jupyter-vue evaluates the script with ``new Function``, which is
      not a module context. Nine of pysepal's own components use it and only
      warn, which is exactly why it looked like the safe choice; in this
      widget it left the grid blank.

    Both failures are silent to every Python-side test, including the ones
    below -- the console is the only place either shows.
    """
    script = _script()
    assert "module.exports" in script
    assert "modules.export" not in script
    assert "export default" not in script


def test_no_cell_value_is_tested_for_truthiness() -> None:
    """``0`` is falsy in JS and is one of this matrix's three values.

    mgci's version reads ``impactCode ? getAbbreviation(...) : ""`` and
    ``if (impactCode)``, which blanks and uncolours every Stable cell. Ours
    compares against ``null`` instead, so the check is that no bare
    truthiness test on a cell value survives.
    """
    script = _script()
    assert "== null" in script, "cell values must be compared against null"
    for banned in ("impactCode ?", "if (impactCode)", "cell.value ?"):
        assert banned not in script, banned


def test_every_icon_the_template_names_exists_in_the_shipped_font() -> None:
    """``tests/app/test_icons.py`` walks ``app/**/*.py`` by AST and so cannot
    see a ``.vue``. An icon the font lacks renders as an empty box, which at
    this size is indistinguishable from nothing at all -- the exact failure
    that test exists for, in the one file it does not reach.
    """
    from tests.app.test_icons import _icons_the_font_has

    font = _icons_the_font_has()
    named = set(re.findall(r"mdi-[a-z0-9-]+", _TEMPLATE.read_text()))
    assert named, "the template names no icons; the scan is broken"
    assert {icon for icon in named if icon[4:] not in font} == set()


# ---------------------------------------------------------------------------
# The Python binding.
# ---------------------------------------------------------------------------


def test_the_widget_is_handed_the_grid_and_the_default_to_reset_to() -> None:
    matrix = TransitionMatrix.default()
    box = _render(matrix, [])

    widget = find_widget(box, TransitionMatrixInput)
    assert widget is not None
    assert widget.matrix == matrix.to_list()
    assert widget.default_matrix == TransitionMatrix.default().to_list()
    assert widget.class_names == list(DEFAULT_LC_CLASS_NAMES)


def test_the_decode_covers_exactly_the_values_a_cell_may_hold() -> None:
    """``validate()`` rejects anything outside {-1, 0, 1}
    (``invalid_transition_matrix``), so a dropdown offering a fourth value
    would build specs the domain refuses."""
    decode = decode_table()
    assert tuple(decode) == CELL_VALUES
    for entry in decode.values():
        assert entry["abrv"] and entry["label"] and entry["color"]


def test_the_decode_reaches_vue_with_string_keys() -> None:
    """A ``Dict`` trait crosses to the browser as JSON, where object keys are
    strings. The template looks up ``decode[String(value)]``; handing it int
    keys would make every lookup miss -- silently, since a missed lookup just
    renders an uncoloured cell."""
    box = _render(TransitionMatrix.default(), [])
    widget = find_widget(box, TransitionMatrixInput)
    assert widget is not None
    assert set(widget.decode) == {"-1", "0", "1"}


@pytest.mark.parametrize("value", CELL_VALUES)
def test_a_cell_edit_produces_a_new_matrix_and_leaves_the_old_one_alone(value: int) -> None:
    """The property the frozen domain type exists for.

    Driving the widget's own trait is what a real edit does: Vue writes the
    whole grid back. ``0`` is one of the cases because it is the value a
    truthiness bug would drop.
    """
    original = TransitionMatrix.default()
    before = original.to_list()
    captured: list[TransitionMatrix] = []
    box = _render(original, captured)

    widget = find_widget(box, TransitionMatrixInput)
    assert widget is not None
    edited = original.to_list()
    edited[0][1] = value
    widget.matrix = edited

    if value == original.rows[0][1]:
        assert captured == [], "an unchanged cell must not rewrite the spec"
        return
    assert len(captured) == 1
    assert captured[0].rows[0][1] == value
    assert original.to_list() == before, "the matrix handed in was mutated"


def test_a_grid_of_strings_round_trips_back_to_ints() -> None:
    """A ``v-select`` can hand its value back as a string. ``from_list``
    coerces, and this is the guard that the binding actually routes through
    it rather than storing whatever arrived."""
    captured: list[TransitionMatrix] = []
    box = _render(TransitionMatrix.default(), captured)

    widget = find_widget(box, TransitionMatrixInput)
    assert widget is not None
    widget.matrix = [[str(cell) for cell in row] for row in TransitionMatrix.default().to_list()]

    # Same values, so nothing should be reported as a change.
    assert captured == []


def test_the_editor_explains_itself_below_the_grid() -> None:
    """The prose sits UNDER the matrix, and the widget carries no heading.

    A subtitle above it read as a sub-panel inside a section that already has
    a header; the description does the same job better after the reader has
    looked at the grid. The cycle hint stays on the widget, since it is a
    per-cell tooltip.
    """
    box = _render(TransitionMatrix.default(), [])
    widget = find_widget(box, TransitionMatrixInput)
    assert widget is not None
    assert not hasattr(widget, "title"), "the grid must not carry a heading of its own"

    assert widget.cycle_label == msg("matrix.cycle")
    assert widget.reset_label == msg("matrix.reset")

    paragraphs = [
        child
        for node in _all(box, v.Html)
        if node.tag == "p"
        for child in (node.children or [])
        if isinstance(child, str)
    ]
    assert paragraphs == [msg("matrix.description")]


def test_the_editor_renders_a_legend_for_every_value() -> None:
    """The cells carry an abbreviation only -- there is no room for a word at
    7x7 in a 450px panel -- so the mapping has to be written down."""
    box = _render(TransitionMatrix.default(), [])

    texts = [
        child
        for span in _all(box, v.Html)
        if span.tag == "span"
        for child in (span.children or [])
        if isinstance(child, str)
    ]
    for entry in decode_table().values():
        assert f"{entry['abrv']} — {entry['label']}" in texts

    # Centred under the grid rather than ragged-left against it.
    row = next(
        d
        for d in _all(box, v.Html)
        if d.tag == "div" and "d-flex" in (d.class_ or "") and "flex-wrap" in (d.class_ or "")
    )
    assert "justify-center" in (row.class_ or "")


def _all(root: object, cls: type) -> list[object]:
    found = [root] if isinstance(root, cls) else []
    for child in getattr(root, "children", None) or []:
        found.extend(_all(child, cls))
    return found
