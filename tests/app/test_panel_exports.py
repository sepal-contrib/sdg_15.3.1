"""Seven export sources, one per layer, the user picks.

``ExportLauncher`` is a real pysepal component that resolves
``get_current_gee_interface()`` / ``get_current_drive_interface()`` /
``get_current_sepal_client()`` synchronously, at render time, unless a
non-``None`` value is threaded in -- see ``exports.py``'s ``ExportsPanel``
docstring. pysepal's own test suite (``solara-export.md``'s testing section)
always passes ``MagicMock()`` for exactly this reason. So the "built" branch
here is checked with a spy standing in for ``ExportLauncher`` itself, never by
rendering the real dialog machinery bare -- that would reach live session
resolution outside a SEPAL runtime, which the domain suite has no fixture for
(``tests/ee_offline.py`` initialises ``ee`` offline, not a SEPAL session).
"""

from __future__ import annotations

from typing import Any

import ipyvuetify
import solara

from app.message import msg
from app.panels.exports import ExportsPanel, export_sources
from sdg1531.spec import RunSpec
from tests.app.render_helpers import find_widget, markdown_texts


def test_the_panel_renders_before_a_run():
    box, rc = solara.render(
        ExportsPanel(maps=None, ctx=None, spec=RunSpec(), gee_interface=None), handle_error=False
    )
    assert rc is not None
    assert markdown_texts(box) == [
        f"<p>{msg('exports.description')}</p>",
        f"<p>{msg('exports.build_first')}</p>",
    ]
    assert find_widget(box, ipyvuetify.Btn) is None  # no dead launcher before Build


def test_the_panel_waits_for_both_maps_and_context():
    """``maps`` and ``ctx`` land together, from one ``build_outcome`` call --
    but they are still two separate fields on that ``BuildOutcome``, so
    nothing stops a caller handing in one without the other. The panel must
    not offer the launcher until both have landed."""
    from app.steps.run import build
    from tests.spec_factory import default_spec

    maps_obj, _ctx_obj = build(default_spec(threshold=0.0))
    box, rc = solara.render(
        ExportsPanel(maps=maps_obj, ctx=None, spec=RunSpec(), gee_interface=None),
        handle_error=False,
    )
    assert rc is not None
    assert markdown_texts(box) == [
        f"<p>{msg('exports.description')}</p>",
        f"<p>{msg('exports.build_first')}</p>",
    ]
    assert find_widget(box, ipyvuetify.Btn) is None


def test_there_is_one_source_per_layer_named_from_the_domain():
    """Asset basenames come from sdg1531.naming, not from the UI: a repeat run
    must produce the same names, and naming.py owns the collision suffix."""
    from app.steps.run import build
    from sdg1531.naming import LAYER_BASENAMES
    from tests.spec_factory import default_spec

    maps, ctx = build(default_spec(threshold=0.0))
    sources = export_sources(maps, ctx)
    assert len(sources) == 7
    assert {s.kind for s in sources} == {"image"}
    for source in sources:
        assert source.id in LAYER_BASENAMES


def test_resolve_is_lazy():
    """pysepal invokes resolve() when the user presses Export, so the AOI clip
    happens at press time. Building the ee object at render would do the work
    for seven layers on every re-render."""
    from app.steps.run import build
    from tests.spec_factory import default_spec

    maps, ctx = build(default_spec(threshold=0.0))
    sources = export_sources(maps, ctx)
    assert all(callable(s.resolve) for s in sources)


def test_resolve_carries_the_legacy_clip_region_scale_and_max_pixels():
    """Defect fix under test: ``ResolvedExport`` defaults ``region`` and
    ``default_scale`` to ``None``, which would export an unbounded footprint
    at a default scale instead of the AOI at the run's analysis scale
    (``component/scripts/gdrive.py:160-170`` clipped and passed both, plus
    ``maxPixels=1e13``). Compared by ``.serialize()``, the idiom the domain
    suite already uses for ``ee`` object equality (see
    ``tests/engine/test_context.py``)."""
    from app.panels.map_layers import layer_vis_params
    from app.steps.run import build
    from sdg1531.naming import LAYER_BASENAMES
    from tests.spec_factory import default_spec

    maps, ctx = build(default_spec(threshold=0.0))
    layers = maps.layers()
    sources = {s.id: s for s in export_sources(maps, ctx)}

    for layer_id, layer in layers.items():
        resolved = sources[layer_id.value].resolve()
        expected_object = layer.image.select(layer.band).clip(ctx.feature_collection)
        assert resolved.ee_object.serialize() == expected_object.serialize()
        assert resolved.region is not None
        assert resolved.region.serialize() == ctx.geometry.serialize()
        assert resolved.default_scale == maps.resolved.analysis_scale
        assert resolved.max_pixels == int(1e13)
        assert resolved.default_name == LAYER_BASENAMES[layer_id.value]
        assert resolved.vis_params == layer_vis_params(layer_id)


def test_the_launcher_is_wired_with_the_localized_label_and_the_threaded_gee_interface(
    monkeypatch,
):
    """A source grep can't tell a hardcoded ``"Export"`` from ``msg(...)``,
    and can't tell a threaded ``gee_interface`` from one left for
    ``ExportLauncher``'s own ``get_current_gee_interface()`` fallback to
    resolve (which raises outside a SEPAL session -- see the module
    docstring). Spying on the real kwargs proves both."""
    from app.steps.run import build
    from tests.spec_factory import default_spec

    captured: dict[str, Any] = {}

    @solara.component
    def _spy_export_launcher(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("app.panels.exports.ExportLauncher", _spy_export_launcher)

    maps_obj, ctx_obj = build(default_spec(threshold=0.0))
    sentinel_gee_interface = object()

    box, rc = solara.render(
        ExportsPanel(
            maps=maps_obj, ctx=ctx_obj, spec=RunSpec(), gee_interface=sentinel_gee_interface
        ),
        handle_error=False,
    )
    assert rc is not None

    assert len(captured["sources"]) == 7
    assert captured["label"] == msg("exports.button")
    assert captured["button_text"] is True
    assert captured["block"] is True
    assert captured["gee_interface"] is sentinel_gee_interface
    # The description still shows (it's not conditional on a build); no
    # stray "build first" text now that one exists.
    assert markdown_texts(box) == [f"<p>{msg('exports.description')}</p>"]
