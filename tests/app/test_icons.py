"""Every ``mdi-`` name the app uses must exist in the font the browser loads.

A Vuetify icon whose name the font does not carry does not fail, warn, or fall
back -- it renders an empty box, and at ``dense`` size an empty box is
indistinguishable from nothing at all. The export icon shipped that way: the
row had ``mdi-tray-arrow-down``, every Python test passed (they assert the
button's ``title``, not its glyph), and the repo owner's report was simply
*"it is not visible, maybe the icon you selected doesn't exist?"*.

It did not. The MDI webfont this stack serves is **4.9.95** -- pinned in
solara's own ``plain.html`` and bundled into the ``jupyter-vuetify``
labextension, 4996 icons -- and ``tray-arrow-down`` arrived in MDI 5. Nothing
in the Python layer can see that, which is exactly why it needs a test: the
font is a real artefact on disk, so the check below reads it rather than
trusting a name that looked plausible.

The roster is taken from string LITERALS via ``ast``, not by grepping the
source text, so prose that mentions a dead icon name -- this docstring's own
``tray-arrow-down``, or the note in ``app/panels/map_layers.py`` -- is not
mistaken for a use of it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from jupyter_core.paths import jupyter_path

#: One MDI class name and nothing else. A docstring that merely CONTAINS an
#: icon name is a longer string and will not match.
_ICON_LITERAL = re.compile(r"mdi-[a-z0-9-]+")

#: How the bundled font declares a glyph: ``.mdi-eye::before { content: ... }``.
_FONT_RULE = re.compile(r"\.mdi-([a-z0-9-]+)::before")

_APP = Path(__file__).resolve().parents[2] / "app"


def _icons_the_app_names() -> dict[str, list[str]]:
    """Every ``mdi-*`` string literal under ``app/``, mapped to where it is."""
    found: dict[str, list[str]] = {}
    for module in sorted(_APP.rglob("*.py")):
        tree = ast.parse(module.read_text(), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and _ICON_LITERAL.fullmatch(str(node.value)):
                where = f"{module.relative_to(_APP.parent)}:{node.lineno}"
                found.setdefault(node.value, []).append(where)
    return found


def _icons_the_font_has() -> frozenset[str]:
    """The glyph names in the MDI webfont the ``jupyter-vuetify`` bundle ships.

    Located through ``jupyter_path`` rather than a guessed ``sys.prefix``
    layout, because that is the same search order the notebook server itself
    uses to find the extension it serves.
    """
    names: set[str] = set()
    for root in jupyter_path("labextensions"):
        static = Path(root) / "jupyter-vuetify" / "static"
        if not static.is_dir():
            continue
        for bundle in static.glob("*.js"):
            names.update(_FONT_RULE.findall(bundle.read_text(errors="ignore")))
    return frozenset(names)


def test_the_font_roster_was_actually_found():
    """The floor under the check below.

    If the bundle moves or the extraction stops matching, ``_icons_the_font_has``
    returns an empty set and "every icon is in the font" passes vacuously --
    the same silent-nothing failure ``tests/app/conftest.py`` exists to stop
    for this whole directory. So the roster's own size is asserted first, and
    a failure here means the LOCATOR is broken, not the icons.
    """
    names = _icons_the_font_has()
    assert len(names) > 1000, (
        "found no MDI webfont to check against -- looked for "
        "jupyter-vuetify/static/*.js under " + ", ".join(jupyter_path("labextensions"))
    )
    assert "eye" in names and "eye-off-outline" in names


def test_the_app_names_icons_at_all():
    """The other half of the floor: an extractor that found nothing would also
    make the check below pass with nothing to check."""
    assert len(_icons_the_app_names()) >= 10


def test_every_icon_the_app_names_exists_in_the_shipped_font():
    """The real check. A name the font lacks renders as an empty box."""
    font = _icons_the_font_has()
    missing = {
        icon: where for icon, where in _icons_the_app_names().items() if icon[4:] not in font
    }
    assert not missing, (
        "these icon names do not exist in the MDI webfont this stack serves, so "
        f"they render as an empty box: {missing}"
    )


@pytest.mark.parametrize("absent", ["mdi-tray-arrow-down", "mdi-not-a-real-icon"])
def test_the_check_would_notice_an_icon_the_font_lacks(absent):
    """Mutation guard, with the real regression as one of its cases:
    ``mdi-tray-arrow-down`` is a genuine MDI 5 icon and a genuinely absent one
    here, so this also pins the font generation rather than merely proving
    that a nonsense string is rejected."""
    assert absent[4:] not in _icons_the_font_has()
