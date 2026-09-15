"""The application shell.

``Sdg1531App`` holds the layout so the same code can serve both runtimes;
``Page`` wraps it with SEPAL session authentication for the Solara server.

``steps_data`` is unsorted -- its DISPLAY order is list order, not ``id``. AOI
is first and Run is last; the tasks that follow insert Productivity, Land
cover and SOC between them.
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
from app.steps.aoi import AoiStep
from app.steps.run import RunStep
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps
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
    """The MapApp shell: five configuration steps, results in the right panel."""
    setup_theme_colors()

    spec = solara.use_reactive(RunSpec())
    maps: solara.Reactive[IndicatorMaps | None] = solara.use_reactive(None)
    ctx: solara.Reactive[ExecutionContext | None] = solara.use_reactive(None)

    gee_interface = get_current_gee_interface()
    theme_state = get_current_theme_state()

    # gee_interface, not gee_session: the session param is deprecated in favour of it
    # (sepal_map.py's __init__ docstring), and passing the interface is what makes the
    # map share this kernel's authenticated session instead of building its own.
    sepal_map = SepalMap(gee=True, theme_state=theme_state, gee_interface=gee_interface)

    # Mounted before anything that calls use_notifications(): the bus is
    # created during render, via solara.use_memo (not an effect), specifically
    # so sibling components in the same render pass can resolve a real
    # notifier -- mounted later, a consumer would get the NoopNotifier
    # fallback instead, which warns loudly (a UserWarning, once per call
    # site), not silently.
    NotificationProvider()

    MapApp.element(
        app_title=msg("app.title"),
        app_icon="mdi-earth",
        main_map=[sepal_map],
        steps_data=[
            {
                "id": 1,
                "name": msg("step.aoi"),
                "icon": "mdi-map-marker-check",
                "display": "step",
                "content": [AoiStep(spec=spec, map_=sepal_map)],
            },
            {
                "id": 5,
                "name": msg("step.run"),
                "icon": "mdi-play-circle-outline",
                "display": "step",
                "content": [RunStep(spec=spec, maps=maps, ctx=ctx)],
            },
        ],
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
