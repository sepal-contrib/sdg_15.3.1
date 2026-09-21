"""The shell renders and is wired the way pysepal requires."""

from __future__ import annotations

from typing import Any

import reacton.core
import solara
from pysepal.mapping.sepal_map import SepalMap
from pysepal.sepalwidgets.vue_app import MapApp

from app import page as page_module
from app import tabs as tabs_module
from app.message import messages, msg
from app.panels import map_layers as map_layers_module
from app.tabs import workflow_tabs
from sdg1531.enums import IndicatorLayer
from sdg1531.spec import AdminAoi
from tests.app.render_helpers import find_widget
from tests.spec_factory import default_spec

#: `threshold=0.0`: `default_spec()`'s MODIS sensor needs a resolved float
#: threshold before `build_indicator_maps()` will succeed -- see
#: `tests/app/test_tabs.py`, which floors its own buildable spec the same way.
_BUILDABLE_SPEC = default_spec(threshold=0.0)


@solara.component
def _noop_export_dialog_host(**_kwargs: Any) -> None:
    """``use_export_dialog`` schedules async work at mount and this harness has
    no running loop -- see ``tests/app/test_tabs.py``'s identical stand-in."""


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


def test_changing_the_spec_takes_the_previous_runs_tiles_off_the_map(monkeypatch):
    """The whole chain the repo owner described, through the real app: *"if I
    change params, the map should gone ... the same if I change the AOI"*.

    Every link is exercised for real -- ``spec`` -> ``build_outcome`` ->
    ``use_memo`` -> ``WorkflowTabs`` -> ``OutputsPanel`` -> ``MapLayersPanel``
    -> ``SepalMap.remove_layer`` -- because the parts that could break it are
    exactly the ones a panel-level test replaces with a fake: whether a real
    ``IndicatorMaps`` from a changed spec actually compares unequal (and
    cheaply -- see ``test_staleness.py``), and whether the panel that owns the
    sweep is even still mounted after a tab switch. Both were verified by
    hand before this test existed; this is what keeps them verified.

    Counting the sweep rather than watching real tiles keeps it offline:
    ``clear_stale_layers`` removes every ``IndicatorLayer`` id on each run
    change, whether or not that layer was ever drawn, so the count is the
    signal.
    """
    removed: list[str] = []
    monkeypatch.setattr(
        page_module.SepalMap,
        "remove_layer",
        lambda self, key, none_ok=False: removed.append(key),
    )
    monkeypatch.setattr(map_layers_module, "_ExportDialogHost", _noop_export_dialog_host)
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["spec"] = spec

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    assert removed == [], "the mount is not a run change"

    captured["spec"].value = _BUILDABLE_SPEC
    rc.force_update()
    after_first_build = len(removed)
    assert after_first_build == len(IndicatorLayer)

    captured["spec"].value = _BUILDABLE_SPEC.evolve(threshold=0.5)  # a PARAMS edit
    rc.force_update()
    assert len(removed) == 2 * len(IndicatorLayer)

    captured["spec"].value = _BUILDABLE_SPEC.evolve(
        threshold=0.5, aoi=AdminAoi(admin_code="76", name="Valle del Cauca")
    )  # an AOI change
    rc.force_update()
    assert len(removed) == 3 * len(IndicatorLayer)
