"""The shell renders and is wired the way pysepal requires."""

from __future__ import annotations

from typing import Any

import reacton.core
import solara
from pysepal.mapping.sepal_map import SepalMap

from app import page as page_module
from app import tabs as tabs_module
from app.message import messages, msg
from app.panels import map_layers as map_layers_module
from app.tabs import workflow_tabs
from sdg1531.enums import IndicatorLayer
from sdg1531.spec import AdminAoi
from tests.app.render_helpers import (
    mapapp_map,
    panel_footer,
    panel_sections,
    widgets_with_class,
)
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


def _walk(root: object) -> list[Any]:
    found = [root]
    for child in getattr(root, "children", None) or []:
        if not isinstance(child, str):
            found.extend(_walk(child))
    return found


def _strings(root: object, icons: bool) -> list[str]:
    return [
        child
        for widget in _walk(root)
        if (type(widget).__name__ == "Icon") is icons
        for child in getattr(widget, "children", None) or []
        if isinstance(child, str)
    ]


def _texts(root: object) -> list[str]:
    return _strings(root, icons=False)


def _icons(root: object) -> list[str]:
    return _strings(root, icons=True)


def _resize(box: object, width: int, height: int) -> None:
    """Report a window size the way the browser does, through the shell's
    ``ViewportBridge`` (the one widget carrying ``css_vars``)."""
    bridge = next(w for w in _walk(box) if hasattr(w, "css_vars"))
    bridge.vue_window_size({"w": width, "h": height})


def test_the_shell_builds_a_correctly_configured_mapapp():
    """A source grep for ``MapApp(`` only proves a spelling. This is the
    behavioural check that dominates it: it reads the shell the native
    ``MapApp`` actually rendered, which the legacy
    ``pysepal.sepalwidgets.vue_app.MapApp`` widget does not render at all,
    and, unlike a grep, it also catches a dropped or misspelled kwarg for
    every field this task gives a genuinely non-empty expected value (an
    empty map, a wrong icon, a wrong panel config, no language selector).
    The title is not drawn by the collapsed drawer ``is_pinned=False`` starts
    with; the narrow-window test below reads it off the top bar.

    The whole workflow lives in ONE ``right_panel_content`` section now, not
    ten (Task 21 moved the ten steps into ``app.tabs.WorkflowTabs``, itself the
    section's sole content) -- the drawer is asserted to hold no step for the
    same reason ``steps_data`` always had to be empty: a leftover copy of a
    step in the old home would render it twice. The section draws no header
    and no description: pysepal renders a section with no ``title``, ``icon``
    or ``description`` as bare content, which is what gives the tab component
    the full panel width (see ``app/tabs.py``'s module docstring). This check
    only proves the section's SHAPE -- that it is titleless and holds one
    item -- not that the one item is really ``WorkflowTabs`` wired to the real
    spec, map and outcome; ``tests/app/test_tabs.py`` proves that identity
    instead.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    _resize(box, 1400, 900)

    (drawer,) = widgets_with_class(box, "sepal-mapapp__drawer")
    assert "sepal-mapapp__drawer--rail" in drawer.class_.split()
    (app_header,) = widgets_with_class(drawer, "sepal-mapapp__app-title")
    assert _icons(app_header) == ["mdi-earth"]
    steps = [
        w for w in _walk(drawer) if "data-step-id" in (getattr(w, "item_attributes", None) or {})
    ]
    assert steps == []

    assert isinstance(mapapp_map(box), SepalMap)

    (panel,) = widgets_with_class(box, "sepal-right-panel")
    assert "sepal-right-panel--open" in panel.class_.split()
    assert panel.style_ == "width: 450px"
    (panel_header,) = widgets_with_class(panel, "sepal-mapapp__app-title")
    assert _icons(panel_header) == ["mdi-format-list-checks"]
    assert _texts(panel_header) == [msg("panel.title")]
    (description,) = widgets_with_class(panel, "panel-description")
    assert _texts(description) == [msg("panel.description")]

    (section,) = panel_sections(box)
    assert len(section) == 1
    assert widgets_with_class(panel, "section-header") == []
    assert widgets_with_class(panel, "section-description") == []

    (selector,) = [w for w in _walk(drawer) if hasattr(w, "available_locales")]
    offered = {locale["code"] for locale in selector.available_locales}
    assert offered == set(messages.available_locales())


def test_a_narrow_window_moves_the_drawer_to_the_top_and_the_panel_to_the_bottom():
    """What moving to the native shell is for: below 960px the drawer becomes a
    bar across the top, which carries the app title, and the panel, with the
    workflow and its footer, docks at the bottom of the window."""
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    _resize(box, 800, 600)

    assert widgets_with_class(box, "sepal-mapapp__drawer") == []
    (belt,) = widgets_with_class(box, "sepal-mapapp__belt")
    (title,) = widgets_with_class(belt, "sepal-mapapp__belt-title")
    assert _texts(title) == [msg("app.title")]

    (panel,) = widgets_with_class(box, "sepal-right-panel")
    assert "sepal-right-panel--narrow" in panel.class_.split()
    assert "sepal-right-panel--open" in panel.class_.split()
    assert [len(section) for section in panel_sections(box)] == [1]
    assert len(panel_footer(box)) == 1


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
    first_map = mapapp_map(box)

    rc.force_update()

    assert mapapp_map(box) is first_map


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
