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
from app.tabs import WorkflowFooter, WorkflowTabs
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
    outcome = solara.use_memo(lambda: build_outcome(spec.value), [spec.value])

    shown_layers = solara.use_reactive(frozenset[IndicatorLayer]())
    # Owned here, not inside `WorkflowTabs`: the footer renders into a
    # separate `MapApp` subtree and drives the same index (`app/tabs.py`).
    active_tab = solara.use_reactive(0)

    gee_interface = get_current_gee_interface()
    theme_state = get_current_theme_state()

    # Keyed on `id(...)`, not the interface itself: without the memo a new
    # SepalMap is built every render, losing the previous one's basemap, zoom
    # and layers.
    sepal_map = solara.use_memo(
        lambda: SepalMap(
            gee=True, fullscreen=True, theme_state=theme_state, gee_interface=gee_interface
        ),
        [id(gee_interface)],
    )

    # Must precede every `use_notifications()` consumer below.
    NotificationProvider()

    # `MapApp`'s sibling, not panel content: it positions itself `fixed`, so
    # it stays visible whichever tab is active.
    MapLegend(maps=outcome.maps, shown=shown_layers)

    MapApp.element(
        app_title=msg("app.title"),
        app_icon="mdi-earth",
        # The drawer holds one item (the map) and nothing the user returns to,
        # so it starts collapsed and re-collapses after use; the whole window
        # is the map and the right panel.
        is_pinned=False,
        main_map=[sepal_map],
        steps_data=[],
        right_panel_config={
            "title": msg("panel.title"),
            "icon": "mdi-format-list-checks",
            "width": 450,
            "description": msg("panel.description"),
        },
        right_panel_content=[
            {
                "content": [
                    WorkflowTabs(
                        spec=spec,
                        sepal_map=sepal_map,
                        outcome=outcome,
                        shown_layers=shown_layers,
                        active_tab=active_tab,
                        gee_interface=gee_interface,
                        sepal_client=get_current_sepal_client(),
                    )
                ],
            },
        ],
        right_panel_open=True,
        theme_state=theme_state,
        locales=messages.available_locales(),
        right_panel_footer=[
            WorkflowFooter(active_tab=active_tab, spec=spec.value, outcome=outcome)
        ],
    )


# Frozen: this is the directory legacy results already live in.
@solara.component
@with_sepal_sessions(module_name="sdg_indicators/degraded_land")
def Page() -> None:
    """Authenticated Solara-server entrypoint."""
    Sdg1531App()
