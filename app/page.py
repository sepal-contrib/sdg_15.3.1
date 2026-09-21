"""The application shell.

``Sdg1531App`` holds the layout so the same code can serve both runtimes;
``Page`` wraps it with SEPAL session authentication for the Solara server.

The whole workflow lives in ``right_panel_content`` as ONE titleless section
whose content is ``app/tabs.py``'s ``WorkflowTabs`` -- pysepal renders a
section with no title, icon or description as bare content, so the tabs get
the full panel width instead of a heading stacked above them.
"""

from __future__ import annotations

from collections.abc import Callable

import solara
from pysepal.mapping.sepal_map import SepalMap
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import (
    get_current_gee_interface,
    get_current_sepal_client,
    get_current_theme_state,
    setup_sessions,
    setup_solara_server,
    setup_theme_colors,
    with_sepal_sessions,
)
from pysepal.solara.notifications import NotificationProvider

from app.message import messages, msg
from app.panels.legend import MapLegend
from app.steps.run import build_outcome
from app.tabs import WorkflowTabs
from sdg1531.enums import IndicatorLayer
from sdg1531.spec import RunSpec

__all__ = ("Page", "Sdg1531App")

setup_solara_server(extra_asset_locations=[])


@solara.lab.on_kernel_start
def _on_kernel_start() -> Callable[[], None]:
    """One SEPAL session per kernel."""
    cleanup: Callable[[], None] = setup_sessions()
    return cleanup


@solara.component
def Sdg1531App() -> None:
    """The MapApp shell: the whole workflow lives in the right panel, as tabs."""
    setup_theme_colors()

    spec = solara.use_reactive(RunSpec())
    # `RunSpec` is plain data, so `use_memo` compares it by value: a re-render
    # that leaves the spec equal reuses the cached outcome, and only a real
    # edit rebuilds. (Its ee-bearing RESULT must never be compared that way --
    # see `app/panels/staleness.py`.)
    outcome = solara.use_memo(lambda: build_outcome(spec.value), [spec.value])

    # Shared with `MapLegend` below and threaded into `WorkflowTabs` ->
    # `MapLayersPanel`: which layers are on the map is state two independent
    # components both need, not something either owns privately. Lives here,
    # next to `spec`, rather than in `app/state.py` -- that module holds pure
    # derivations over `RunSpec` and owns no reactive of its own; this is the
    # same kind of per-render shared reactive `spec` already is.
    shown_layers = solara.use_reactive(frozenset[IndicatorLayer]())

    gee_interface = get_current_gee_interface()
    theme_state = get_current_theme_state()

    # `gee_interface`, not the deprecated `gee_session`, so the map shares this
    # kernel's authenticated session. Memoized on `id(gee_interface)`: without
    # it a new SepalMap is built every render, discarding the previous one's
    # basemap, zoom and layers.
    sepal_map = solara.use_memo(
        lambda: SepalMap(
            gee=True, fullscreen=True, theme_state=theme_state, gee_interface=gee_interface
        ),
        [id(gee_interface)],
    )

    # Mounted before anything that calls use_notifications(): the bus is
    # created during render, via solara.use_memo (not an effect), specifically
    # so sibling components in the same render pass can resolve a real
    # notifier -- mounted later, a consumer would get the NoopNotifier
    # fallback instead, which warns loudly (a UserWarning, once per call
    # site), not silently.
    NotificationProvider()

    # Mounted as `MapApp`'s SIBLING, not inside `right_panel_content`: the
    # legend's own Vue template is `position: fixed` bottom-centre, so it
    # stays visible over the map regardless of which workflow tab is active
    # (the same placement pysepal's own demo app uses).
    MapLegend(maps=outcome.maps, shown=shown_layers)

    MapApp.element(
        app_title=msg("app.title"),
        app_icon="mdi-earth",
        main_map=[sepal_map],
        steps_data=[],
        # A chart icon and the title "Results" were accurate while this panel
        # held only the five output panels. Task 18 moved the whole workflow
        # here and Task 21 tabbed it, so the panel now opens on AOI selection
        # and holds the five configuration steps too -- "mdi-format-list-checks"
        # and "Workflow" describe the whole titleless section, not one tab in it.
        right_panel_config={
            "title": msg("panel.title"),
            "icon": "mdi-format-list-checks",
            "width": 450,
            "description": msg("panel.description"),
        },
        # ONE titleless section: pysepal's RightPanel.vue renders a section with
        # no `title`, `icon` or `description` as bare content, so the tab
        # component gets the full panel width instead of a stacked heading per
        # step. See `app/tabs.py`'s module docstring for why -- the owner asked
        # for the workflow in the right panel AND for the steps to be tabs; this
        # is the reference app's structure for doing both at once.
        right_panel_content=[
            {
                "content": [
                    WorkflowTabs(
                        spec=spec,
                        sepal_map=sepal_map,
                        outcome=outcome,
                        shown_layers=shown_layers,
                        gee_interface=gee_interface,
                        sepal_client=get_current_sepal_client(),
                    )
                ],
            },
        ],
        right_panel_open=True,
        theme_state=theme_state,
        locales=messages.available_locales(),
    )


@solara.component
@with_sepal_sessions(module_name="sdg_15_3_1")
def Page() -> None:
    """Authenticated Solara-server entrypoint."""
    Sdg1531App()
