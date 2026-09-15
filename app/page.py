"""The application shell.

``Sdg1531App`` holds the layout so the same code can serve both runtimes;
``Page`` wraps it with SEPAL session authentication for the Solara server.

``steps_data`` is unsorted -- its DISPLAY order is list order, not ``id``. AOI
is first and Run is last; Productivity, Land cover and SOC sit between them,
in that order (see ``build_steps_data``).
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
from app.steps.land_cover import LandCoverStep
from app.steps.productivity import ProductivityStep
from app.steps.run import RunStep
from app.steps.soc import SocStep
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps
from sdg1531.spec import RunSpec

__all__ = ("Page", "Sdg1531App", "build_steps_data")

setup_solara_server(extra_asset_locations=[])


def build_steps_data(
    spec: solara.Reactive[RunSpec] | None = None,
    sepal_map: SepalMap | None = None,
    maps: solara.Reactive[IndicatorMaps | None] | None = None,
    ctx: solara.Reactive[ExecutionContext | None] | None = None,
) -> list[dict[str, object]]:
    """The five configuration steps, in DISPLAY order.

    List position, not ``id``, is what orders them -- ``MapApp.vue`` returns
    ``steps_data`` as given. AOI -> Productivity -> Land cover -> SOC -> Run
    (design decision A6); Run's own ``id`` reads 5 even though SOC (id 4) was
    the task added after it.

    Every argument defaults to ``None`` so this is reachable with no render
    context at all -- calling a ``@solara.component`` function outside a
    render pass builds an inert element descriptor, never executes the
    component body, so ``tests/app/test_page.py`` can call
    ``build_steps_data()`` bare to pin step order (id, name, icon, display)
    without a real spec, map or reactive to hand it. Each step's own content
    is built only once its required reactives are actually present, guarded
    with plain ``is not None`` checks -- calling a step with ``None`` would
    not actually raise (an inert element descriptor is built either way, per
    the paragraph above), so this buys nothing at runtime. It exists solely
    so ``mypy --strict`` narrows each ``Reactive[...] | None`` argument away
    from ``None`` before it reaches a step that declares a bare
    ``Reactive[...]`` parameter; measured by deleting the guards, which
    leaves every test green and produces one ``mypy`` error per guard removed.
    """
    aoi_content: list[object] = (
        [AoiStep(spec=spec, map_=sepal_map)] if spec is not None and sepal_map is not None else []
    )
    productivity_content: list[object] = [ProductivityStep(spec=spec)] if spec is not None else []
    land_cover_content: list[object] = [LandCoverStep(spec=spec)] if spec is not None else []
    soc_content: list[object] = [SocStep(spec=spec)] if spec is not None else []
    run_content: list[object] = (
        [RunStep(spec=spec, maps=maps, ctx=ctx)]
        if spec is not None and maps is not None and ctx is not None
        else []
    )
    return [
        {
            "id": 1,
            "name": msg("step.aoi"),
            "icon": "mdi-map-marker-check",
            "display": "step",
            "content": aoi_content,
        },
        {
            "id": 2,
            "name": msg("step.productivity"),
            "icon": "mdi-sprout-outline",
            "display": "step",
            "content": productivity_content,
        },
        {
            "id": 3,
            "name": msg("step.land_cover"),
            "icon": "mdi-terrain",
            "display": "step",
            "content": land_cover_content,
        },
        {
            "id": 4,
            "name": msg("step.soc"),
            "icon": "mdi-layers-outline",
            "display": "step",
            "content": soc_content,
        },
        {
            "id": 5,
            "name": msg("step.run"),
            "icon": "mdi-play-circle-outline",
            "display": "step",
            "content": run_content,
        },
    ]


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
        steps_data=build_steps_data(spec=spec, sepal_map=sepal_map, maps=maps, ctx=ctx),
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
