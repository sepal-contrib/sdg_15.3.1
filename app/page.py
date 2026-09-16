"""The application shell.

``Sdg1531App`` holds the layout so the same code can serve both runtimes;
``Page`` wraps it with SEPAL session authentication for the Solara server.

The whole workflow lives in ``right_panel_content``, not ``steps_data`` --
the repo owner asked for the ``sbae-design`` / ``sepal-gee-bundle`` layout,
then separately for the ten steps to be tabs. ``app/tabs.py``'s
``WorkflowTabs`` does both at once, the way ``spatial-risk-module`` /
``spatial-risk-main-branch``'s own ``WorkflowTabs`` does: ONE titleless
section whose whole content is that single component (this supersedes
decision A6's PLACEMENT a second time; the ORDER it chose is unchanged). List
position, not any key, is still what orders the ten tabs inside it: AOI is
first and Export is last; Productivity, Land cover, SOC and Run sit between
them, then Layers, Transitions, Results and Zonal after Run, in that order
(see ``app.tabs.workflow_tabs``). ``steps_data`` is left empty -- this app
has no non-workflow entry (an About dialog, say) to put there.
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
from app.steps.run import build_outcome
from app.tabs import WorkflowTabs
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
