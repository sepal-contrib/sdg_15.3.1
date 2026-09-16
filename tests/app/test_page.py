"""The shell renders and is wired the way pysepal requires."""

from __future__ import annotations

import reacton.core
import solara
from pysepal.mapping.sepal_map import SepalMap
from pysepal.sepalwidgets.vue_app import MapApp

from app import page as page_module
from app.message import messages, msg
from app.tabs import workflow_tabs
from tests.app.render_helpers import find_widget


def test_page_is_a_solara_component():
    # reacton.core.Component, not solara.core.Component -- the latter does not
    # exist. @solara.component returns a reacton ComponentFunction, which is a
    # reacton.core.Component; solara re-exports no Component name at all.
    assert isinstance(page_module.Page, reacton.core.Component)
    assert isinstance(page_module.Sdg1531App, reacton.core.Component)


def test_the_shell_renders():
    """A render that raises takes the whole app down at load; this is the
    cheapest possible guard against that."""
    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None


def test_the_shell_builds_a_correctly_configured_mapapp():
    """A source grep for ``MapApp.element(`` only proves a spelling. This is
    the behavioural check that dominates it: ``MapApp(...)`` builds a widget
    outside Reacton's render tree, so no ``MapApp`` instance is reachable from
    the rendered box at all under that mistake -- and, unlike a grep, it also
    catches a dropped or misspelled kwarg for every field this task gives a
    genuinely non-empty expected value (an empty map, a wrong title, a wrong
    panel config, no language selector).

    The whole workflow lives in ONE ``right_panel_content`` section now, not
    ten (Task 21 moved the ten steps into ``app.tabs.WorkflowTabs``, itself the
    section's sole content) -- ``steps_data`` is asserted empty here for the
    same reason it always was: a leftover copy of a step in the old home would
    render it twice. The section carries no ``title``/``icon``/``description``
    at all: pysepal's ``RightPanel.vue`` renders a section with none of those
    as bare content, which is what gives the tab component the full panel
    width (see ``app/tabs.py``'s module docstring). This check only proves the
    section's SHAPE -- that it is titleless and its content is length 1 --
    not that the one item is really ``WorkflowTabs`` wired to the real spec,
    map and outcome; ``tests/app/test_tabs.py`` proves that identity instead.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    mapapp = find_widget(box, MapApp)
    assert mapapp is not None, "no MapApp in the render tree; MapApp(...) builds outside it"

    assert mapapp.app_title == msg("app.title")
    assert mapapp.app_icon == "mdi-earth"
    assert len(mapapp.main_map) == 1
    assert isinstance(mapapp.main_map[0], SepalMap)
    assert mapapp.right_panel_config == {
        "title": msg("panel.title"),
        "icon": "mdi-format-list-checks",
        "width": 450,
        "description": msg("panel.description"),
    }
    assert mapapp.steps_data == []
    assert len(mapapp.right_panel_content) == 1
    workflow_section = mapapp.right_panel_content[0]
    assert set(workflow_section.keys()) == {"content"}
    assert len(workflow_section["content"]) == 1
    assert mapapp.right_panel_open is True
    assert len(mapapp.language_selector) == 1
    offered = {locale["code"] for locale in mapapp.language_selector[0].available_locales}
    assert offered == set(messages.available_locales())


def test_the_panel_title_names_no_single_tab_it_contains():
    """A title is a judgement about meaning, not a property a unit test can
    verify is TRUE -- but "Results" (Task 18-21's regression: the panel held
    only five output panels when it was named that, then grew the other five
    configuration steps around it) is a judgement a test CAN show is FALSE:
    the panel's own title equalling one of the ten tabs' own titles is
    exactly the shape of the error that happened here, a panel named after
    one of the things it contains rather than the whole of it.

    Tab titles come from ``workflow_tabs()`` itself, callable with no render
    context per its own docstring -- not a second, hand-typed list of ten
    strings that could silently drift from the real tab order.
    """
    tab_titles = {tab.title for tab in workflow_tabs()}
    assert msg("panel.title") not in tab_titles


def test_the_map_is_memoized_across_rerenders():
    """``Sdg1531App`` used to build a brand-new ``SepalMap`` on every render,
    discarding the previous one's basemap, zoom and layers each time.
    ``solara.use_memo``, keyed on ``id(gee_interface)``, is supposed to
    prevent that -- proven here by forcing a second render and checking the
    SAME ``SepalMap`` instance comes back, not merely another one that would
    also pass an ``isinstance`` check.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    mapapp = find_widget(box, MapApp)
    assert mapapp is not None
    first_map = mapapp.main_map[0]

    rc.force_update()

    mapapp_again = find_widget(box, MapApp)
    assert mapapp_again is not None
    assert mapapp_again.main_map[0] is first_map
