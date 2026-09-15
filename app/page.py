"""The application shell.

``Sdg1531App`` holds the layout so the same code can serve both runtimes;
``Page`` wraps it with SEPAL session authentication for the Solara server.

The steps are empty at this task and are filled in by the tasks that follow.
"""

from __future__ import annotations

from collections.abc import Callable

import solara
from pysepal.mapping.sepal_map import SepalMap
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import (
    get_current_gee_interface,
    get_current_theme_state,
    setup_sessions,
    setup_solara_server,
    setup_theme_colors,
    with_sepal_sessions,
)
from pysepal.solara.notifications import NotificationProvider

from app.message import messages, msg

__all__ = ("Page", "Sdg1531App")

setup_solara_server(extra_asset_locations=[])


@solara.lab.on_kernel_start
def _on_kernel_start() -> Callable[[], None]:
    """One SEPAL session per kernel."""
    cleanup: Callable[[], None] = setup_sessions()
    return cleanup


@solara.component
def Sdg1531App() -> None:
    """The MapApp shell: five configuration steps, results in the right panel."""
    setup_theme_colors()

    gee_interface = get_current_gee_interface()
    theme_state = get_current_theme_state()

    # gee_interface, not gee_session: the session param is deprecated in favour of it
    # (sepal_map.py's __init__ docstring), and passing the interface is what makes the
    # map share this kernel's authenticated session instead of building its own.
    sepal_map = SepalMap(gee=True, theme_state=theme_state, gee_interface=gee_interface)

    # Mounted before anything that calls use_notifications(): on the first
    # render before the provider's effect fires, the hook returns a silent
    # no-op notifier.
    NotificationProvider()

    MapApp.element(
        app_title=msg("app.title"),
        app_icon="mdi-earth",
        main_map=[sepal_map],
        steps_data=[],
        right_panel_config={
            "title": msg("panel.title"),
            "icon": "mdi-chart-box-outline",
            "width": 450,
            "description": msg("panel.description"),
        },
        right_panel_content=[],
        right_panel_open=False,
        theme_state=theme_state,
        locales=messages.available_locales(),
    )


@solara.component
@with_sepal_sessions(module_name="sdg_15_3_1")
def Page() -> None:
    """Authenticated Solara-server entrypoint."""
    Sdg1531App()
