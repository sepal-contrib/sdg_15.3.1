"""Seven export sources, one per layer, the user picks.

``app/panels/exports.py`` renders nothing any more: the Export section it used
to own was folded into the layers table, whose rows each carry their own
export icon (the repo owner asked for it -- see that module's docstring). So
the render-level tests that lived here -- the "build first" placeholder, and
the launcher's own wiring -- moved to ``tests/app/test_panel_map_layers.py``,
where the dialog is now mounted. What stays is the part that was always this
module's real subject: the SOURCES, which are pure and need no render tree at
all.
"""

from __future__ import annotations

from app.panels.exports import export_sources


def test_there_is_one_source_per_layer_and_its_id_matches_a_domain_basename():
    """Asset basenames come from sdg1531.naming, not from the UI: a repeat run
    must produce the same names, and naming.py owns the collision suffix.

    Renamed from ``..._named_from_the_domain``: this only ever checked
    ``source.id``, never the displayed ``source.label`` -- the old name
    overstated what it proved. See
    ``test_each_source_label_is_the_translated_layer_name_not_the_raw_id``
    for the label itself, which (after M1) is no longer "from the domain"
    at all.
    """
    from app.steps.run import build
    from sdg1531.naming import LAYER_BASENAMES
    from tests.spec_factory import default_spec

    maps, ctx = build(default_spec(threshold=0.0))
    sources = export_sources(maps, ctx)
    assert len(sources) == 7
    assert {s.kind for s in sources} == {"image"}
    for source in sources:
        assert source.id in LAYER_BASENAMES


def test_each_source_label_is_the_translated_layer_name_not_the_raw_id():
    """Final-review finding M1: the domain's ``ClassifiedLayer.label`` is the
    raw snake id, and this panel used to pass it straight through as the
    label the user picks the export by.

    Checked against the raw id directly (``!= layer_id.value``), not only
    against ``layer_name(...)`` -- a label that regressed to the raw id
    together with a same-shaped regression in ``layer_name`` itself would
    still agree with a check that only compared the two against each other.
    """
    from app.panels.map_layers import layer_name
    from app.steps.run import build
    from sdg1531.enums import IndicatorLayer
    from tests.spec_factory import default_spec

    maps, ctx = build(default_spec(threshold=0.0))
    sources = {s.id: s for s in export_sources(maps, ctx)}

    for layer_id in IndicatorLayer:
        source = sources[layer_id.value]
        assert source.label != layer_id.value
        assert source.label == layer_name(layer_id)


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
