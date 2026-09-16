"""The application shell.

``Sdg1531App`` holds the layout so the same code can serve both runtimes;
``Page`` wraps it with SEPAL session authentication for the Solara server.

The five configuration steps live in ``right_panel_content``, not
``steps_data`` -- the repo owner asked for the ``sbae-design`` /
``sepal-gee-bundle`` layout, where the whole workflow sits in the right panel
as titled sections and the drawer holds none of it (this supersedes decision
A6's PLACEMENT; the ORDER it chose is unchanged). List position, not any key,
is still what orders them: AOI is first and Run is last; Productivity, Land
cover and SOC sit between them, in that order (see ``build_workflow_sections``).
``steps_data`` is left empty -- this app has no non-workflow entry (an About
dialog, say) to put there.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
from app.panels.exports import ExportsPanel
from app.panels.map_layers import MapLayersPanel
from app.panels.results import ResultsPanel
from app.panels.transitions import TransitionsPanel
from app.panels.zonal import ZonalPanel
from app.steps.aoi import AoiStep
from app.steps.land_cover import LandCoverStep
from app.steps.productivity import ProductivityStep
from app.steps.run import BuildOutcome, RunStep, build_outcome
from app.steps.soc import SocStep
from sdg1531.spec import RunSpec

__all__ = ("Page", "Sdg1531App", "build_workflow_sections")

setup_solara_server(extra_asset_locations=[])


def build_workflow_sections(
    spec: solara.Reactive[RunSpec] | None = None,
    sepal_map: SepalMap | None = None,
    outcome: BuildOutcome | None = None,
    gee_interface: Any = None,
) -> list[dict[str, object]]:
    """The five configuration steps, as ``right_panel_content`` sections, in DISPLAY order.

    List position is still what orders them -- ``MapApp.vue`` renders
    ``right_panel_content`` as given -- but a section has no ``id`` for a
    stray sort to key on (unlike a ``steps_data`` entry), so order lives in
    list position alone. AOI -> Productivity -> Land cover -> SOC -> Run
    (design decision A6, unchanged by the move out of ``steps_data``).

    Every argument defaults to ``None`` so this is reachable with no render
    context at all -- calling a ``@solara.component`` function outside a
    render pass builds an inert element descriptor, never executes the
    component body, so ``tests/app/test_page.py`` can call
    ``build_workflow_sections()`` bare to pin section order (title, icon)
    without a real spec, map or outcome to hand it. Each step's own content
    is built only once its required arguments are actually present, guarded
    with plain ``is not None`` checks -- calling a step with ``None`` would
    not actually raise (an inert element descriptor is built either way, per
    the paragraph above), so this buys nothing at runtime. It exists solely
    so ``mypy --strict`` narrows each ``X | None`` argument away from
    ``None`` before it reaches a step that declares a bare ``X`` parameter
    (``Reactive[RunSpec]`` for ``spec``, plain ``BuildOutcome`` for
    ``outcome``); measured by deleting the guards, which leaves every test
    green and produces one ``mypy`` error per guard removed.

    No ``description`` key: each step still renders its own
    ``msg("<step>.description")`` internally (unlike ``MapLayersPanel``, which
    dropped that call in favour of the section's ``description`` field --
    see ``map_layers.py``). Adding one here without touching the step bodies
    would print the sentence twice.
    """
    aoi_content: list[object] = (
        [AoiStep(spec=spec, map_=sepal_map)] if spec is not None and sepal_map is not None else []
    )
    productivity_content: list[object] = [ProductivityStep(spec=spec)] if spec is not None else []
    # No `gee_interface is not None` guard: `LandCoverStep`'s own parameter already
    # defaults to `None` (`AssetSelectComponent` falls back to the session
    # interface), so there is no bare `Reactive[...]` for mypy to narrow here.
    land_cover_content: list[object] = (
        [LandCoverStep(spec=spec, gee_interface=gee_interface)] if spec is not None else []
    )
    soc_content: list[object] = [SocStep(spec=spec)] if spec is not None else []
    run_content: list[object] = (
        [RunStep(spec=spec, outcome=outcome)] if spec is not None and outcome is not None else []
    )
    return [
        {"title": msg("step.aoi"), "icon": "mdi-map-marker-check", "content": aoi_content},
        {
            "title": msg("step.productivity"),
            "icon": "mdi-sprout-outline",
            "content": productivity_content,
        },
        {"title": msg("step.land_cover"), "icon": "mdi-terrain", "content": land_cover_content},
        {"title": msg("step.soc"), "icon": "mdi-layers-outline", "content": soc_content},
        {
            "title": msg("step.run"),
            "icon": "mdi-play-circle-outline",
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
    """The MapApp shell: the five configuration steps and results live in the right panel."""
    setup_theme_colors()

    spec = solara.use_reactive(RunSpec())
    # `RunSpec` is a frozen, slots dataclass of plain data -- no `ee` objects --
    # so it compares by field equality, not identity (`dataclasses.dataclass`'s
    # generated `__eq__`). reacton's `use_memo` compares its dependency list the
    # same way (`reacton.utils.equals`, which falls through to `==` for any type
    # it has no special case for), so an unrelated re-render that leaves `spec`
    # equal to what it already was does NOT recompute this -- only a real edit
    # does. Measured, not assumed: a re-render with a structurally-equal-but-new
    # `RunSpec` object reuses the cached outcome; changing one nested field
    # (`periods.overall`, say) recomputes it.
    outcome = solara.use_memo(lambda: build_outcome(spec.value), [spec.value])

    gee_interface = get_current_gee_interface()
    theme_state = get_current_theme_state()

    # gee_interface, not gee_session: the session param is deprecated in favour of it
    # (sepal_map.py's __init__ docstring), and passing the interface is what makes the
    # map share this kernel's authenticated session instead of building its own.
    #
    # Wrapped in use_memo, keyed on id(gee_interface): without it a new SepalMap
    # widget was built on every render, discarding the previous one's basemap,
    # zoom and layers each time. sepal-gee-bundle's tmf_sepal/page.py, the
    # layout reference for this task, memoizes the same way.
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
        right_panel_content=[
            *build_workflow_sections(
                spec=spec, sepal_map=sepal_map, outcome=outcome, gee_interface=gee_interface
            ),
            {
                "title": msg("layers.title"),
                "icon": "mdi-layers",
                "content": [
                    MapLayersPanel(maps=outcome.maps, map_=sepal_map, gee_interface=gee_interface)
                ],
                "description": msg("layers.description"),
            },
            {
                "title": msg("transitions.title"),
                "icon": "mdi-transit-transfer",
                "content": [
                    TransitionsPanel(
                        maps=outcome.maps, ctx=outcome.ctx, gee_interface=gee_interface
                    )
                ],
                "description": msg("transitions.description"),
            },
            {
                "title": msg("results.title"),
                "icon": "mdi-chart-bar",
                "content": [
                    ResultsPanel(maps=outcome.maps, ctx=outcome.ctx, gee_interface=gee_interface)
                ],
                "description": msg("results.description"),
            },
            {
                "title": msg("zonal.title"),
                "icon": "mdi-table",
                "content": [
                    ZonalPanel(
                        maps=outcome.maps,
                        ctx=outcome.ctx,
                        gee_interface=gee_interface,
                        sepal_client=get_current_sepal_client(),
                    )
                ],
                "description": msg("zonal.description"),
            },
            {
                "title": msg("exports.title"),
                "icon": "mdi-export-variant",
                "content": [
                    ExportsPanel(
                        maps=outcome.maps,
                        ctx=outcome.ctx,
                        spec=spec.value,
                        gee_interface=gee_interface,
                    )
                ],
                "description": msg("exports.description"),
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
