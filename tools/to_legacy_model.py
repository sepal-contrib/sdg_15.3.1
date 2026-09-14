"""RunSpec -> the legacy IndicatorModel. Stage A only.

This is the single reviewed adapter between the two data models, and the port
deliberately ships no live UI adapter beside it. It runs against the legacy tree,
so it imports ``component``.
It is deliberately dumb: every mapping below is a line-for-line reading of
component/model/indicator_model.py's traits, and nothing here is imported by
sdg1531.

Every golden graph is only as correct as this file. If it mis-populates one
trait, the goldens record a legacy run nobody asked for and the port is then
validated against it -- with the suite green. So each assignment below cites the
legacy line that READS the value (not just the line that declares the trait), and
the traits the compute path never reads are named and left alone rather than
guessed at.

The traits the legacy science actually reads, from
``grep -o 'model\\.[a-z_]*' component/scripts/*.py`` plus run_15_3_1.py:164-204:

  direct    start end trend_start trend_end state_start state_end
            performance_start performance_end sensors vegetation_index threshold
            productivity_lookup_table trajectory lceu conversion_coef
            start_lc end_lc water_mask_pixel water_mask_asset_id
            water_mask_asset_band seasonality
  derived   scale (:74-76, off sensors)
            p_trend_* p_state_* p_performance_* p_soc_t_* (:81-153)
            lc_year_start_esa lc_year_end_esa (:156-168, off landcover_t_*)
            lc_class_combination trans_matrix_flatten (:221-242, off start_lc,
            end_lc, custom_matrix_file and transition_matrix)

Three input traits are never read on the compute path and are therefore left at
their declared defaults rather than invented here: ``start_lc_band`` (:61) and
``end_lc_band`` (:63), which input_tile.py:209-211 binds and nothing consumes,
and ``lc_pixel_check`` (:70), which is the ``exact`` argument to
``check_custom_lc_codes`` in the tile layer. ``integrated_vi_asset``
(integration.py:80) is not a trait of IndicatorModel at all -- its branch is
unreachable, and :func:`to_legacy_model` refuses the spec arm that would take it.
``folder_name()`` (:280-312) is not on the compute path either, so the
per-pixel-climate ``TypeError`` it raises at :310 never fires here.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ee

from component.model.indicator_model import IndicatorModel
from sdg1531.spec import (
    AdminAoi,
    AssetAoi,
    AssetBandMask,
    CustomLandCoverSource,
    EsaCciSource,
    FixedClimate,
    GeoJsonAoi,
    JrcSeasonalityMask,
    PerPixelClimate,
    PixelValueMask,
    RunSpec,
    SensorSelection,
)

__all__ = ["LegacyAoi", "to_legacy_model", "write_matrix_csv"]


@dataclass
class LegacyAoi:
    """The three attributes the legacy reads off ``aoi_model``.

    Only ``feature_collection`` is read on the compute path -- integration.py:22,
    :58, :73, :85, productivity.py:143, land_cover.py:10 and
    soil_organic_carbon.py:9, :21. ``name`` and ``method`` are read by
    ``download_maps`` (run_15_3_1.py:176) and ``display_maps`` (:103), neither of
    which builds a graph. They are carried anyway so the stand-in is a faithful
    shape, not so the science can consume them.
    """

    feature_collection: Any
    name: str
    method: str


def write_matrix_csv(scheme: Any, path: Path) -> Path:
    """Write the CSV layout indicator_model.csv_reader() expects.

    Row 0: two filler cells then the end class names (read at :185).
    Row 1: two filler cells then the end class codes (read at :206).
    Rows 2+: start name, start code, then the transition row (read at :179, :195, :215).

    The two filler cells are the legacy template's own header labels
    (utils/ipccsx_matrix.csv row 0 is ``Land cover,<end year>,...``), and nothing
    reads them: every property slices from index 2. Only the CODES and the
    transition VALUES reach a graph, through ``lc_class_combination`` (:221-227)
    and ``trans_matrix_flatten`` (:231-242). The NAMES are re-scrubbed by
    :185-187 / :195-197 and used for labels and colours only.
    """
    rows: list[list[str]] = []
    rows.append(["", ""] + [str(name) for name in scheme.end_names])
    rows.append(["", ""] + [str(code) for code in scheme.end_codes])
    for name, code, matrix_row in zip(
        scheme.start_names, scheme.start_codes, scheme.matrix.to_list(), strict=True
    ):
        rows.append([str(name), str(code)] + [str(v) for v in matrix_row])
    with path.open("w", newline="") as handle:
        csv.writer(handle).writerows(rows)
    return path


def _verify_custom_matrix_roundtrip(model: IndicatorModel, scheme: Any) -> None:
    """Read the CSV back through the LEGACY's own properties and check it survived.

    :func:`write_matrix_csv` is the only part of this adapter that does real work,
    and the two values it feeds into a graph -- ``lc_class_combination`` (:221-227)
    and ``trans_matrix_flatten`` (:231-242) -- are the ``remap`` arguments at
    land_cover.py:92-94. A CSV written in a layout the legacy parses differently
    would still produce a plausible golden, and the port would then be blamed for
    the mismatch. Asserting here instead means stage A fails loudly, in the
    adapter, where the fault would actually be.

    This compares the legacy's parse against the scheme the spec already carries.
    It is not a graph derived from ``sdg1531``; it is the same CSV read twice, by
    the two parsers that are supposed to agree about it.
    """
    checks = (
        ("lc_classlist_end", model.lc_classlist_end, list(scheme.end_names)),
        ("lc_classlist_start", model.lc_classlist_start, list(scheme.start_names)),
        ("lc_codelist_end", model.lc_codelist_end, list(scheme.end_codes)),
        ("lc_codelist_start", model.lc_codelist_start, list(scheme.start_codes)),
        ("lc_class_combination", model.lc_class_combination, list(scheme.class_combinations)),
        ("trans_matrix_flatten", model.trans_matrix_flatten, list(scheme.matrix.flatten())),
    )
    for name, legacy_value, scheme_value in checks:
        if legacy_value != scheme_value:
            raise AssertionError(
                f"write_matrix_csv wrote a CSV the legacy reads back differently: "
                f"IndicatorModel.{name} is {legacy_value!r}, the spec's scheme says "
                f"{scheme_value!r}"
            )


def _feature_collection(aoi: Any) -> Any:
    """The AOI collection, spelled exactly as ``ExecutionContext.from_aoi_spec`` spells it.

    The AOI is an INPUT to both trees, not a thing under test: parity is about the
    science built on top of it. Both sides must therefore build it from the same
    expression, or every graph would differ at its leaves for a reason that has
    nothing to do with the port. See sdg1531/engine/context.py:56-62.
    """
    if isinstance(aoi, AssetAoi):
        return ee.FeatureCollection(aoi.asset_id)
    if isinstance(aoi, GeoJsonAoi):
        return ee.FeatureCollection(aoi.geojson)
    if isinstance(aoi, AdminAoi):
        import pygaul

        return pygaul.Items(admin=aoi.admin_code)
    raise TypeError(f"unsupported aoi arm: {type(aoi).__name__}")


def _method(aoi: Any) -> str:
    # display_maps():103 only tests for "ADMIN"; the science itself never reads it.
    return "ASSET" if isinstance(aoi, AssetAoi) else "ADMIN"


def to_legacy_model(spec: RunSpec, workdir: Path) -> tuple[IndicatorModel, LegacyAoi]:
    """Build the mutable legacy model that reproduces ``spec``."""
    model = IndicatorModel()

    # periods: indicator_model.py:16-32, read through the p_* properties at
    # :81-153. Those test TRUTHINESS, not `is not None`, so None and 0 fall back
    # to start/end alike -- PeriodOverride.resolve() transcribes exactly that.
    model.start = spec.periods.overall.start
    model.end = spec.periods.overall.end
    model.trend_start = spec.periods.trend.start
    model.trend_end = spec.periods.trend.end
    model.state_start = spec.periods.state.start
    model.state_end = spec.periods.state.end
    model.performance_start = spec.periods.performance.start
    model.performance_end = spec.periods.performance.end
    model.landcover_t_start = spec.periods.land_cover.start
    model.landcover_t_end = spec.periods.land_cover.end
    model.soc_t_start = spec.periods.soc.start
    model.soc_t_end = spec.periods.soc.end

    # vi source: :35, read at integration.py:42, :45-92 and by `scale` (:76).
    # PrecomputedViAsset has no legacy branch that works (integration.py:80 reads
    # `model.integrated_vi_asset`, which is not a trait), so it is refused here.
    if not isinstance(spec.vi_source, SensorSelection):
        raise ValueError(
            "PrecomputedViAsset has no reachable legacy branch; it cannot be a parity scenario."
        )
    # sensor_select.py binds a v.Select(multiple=True), whose v_model is a list of
    # the pm.sensors keys -- hence list(), not tuple().
    model.sensors = list(spec.vi_source.names)

    # :38, read at integration.py:49, :63, :88 -- compared against the plain
    # strings "ndvi"/"evi"/"msvi" and `.upper()`ed at :116, so the widget's own
    # value (parameter/ui.py:5-9) is the enum's `.value`, not the member.
    model.vegetation_index = spec.vegetation_index.value
    # :41, read at integration.py:411 (`img.gt(threshold)`). input_tile.py:31-38
    # is a slider over [-1, 1] step 0.01, so a float is what the widget produces.
    model.threshold = spec.threshold
    # :44, read at run_15_3_1.py:184 to pick productivity_final vs _GPG1.
    model.productivity_lookup_table = spec.productivity_lookup.value
    # :49, read at productivity.py:29-49 against pm.trajectories[i]["value"].
    model.trajectory = spec.trajectory.value
    # :50, read at productivity.py:92-116 against "gaes"/"aez"/"hru"/"calculate"
    # /"wte". The dispatch runs to :116; "wte" is its last branch (:115-116) and
    # five corpus rows use it (s03, s08, s13, s18, s23), two of them with goldens.
    model.lceu = spec.lceu.value
    # :53, read through trans_matrix_flatten (:239-241) as a list of lists of int,
    # which is the shape of pm.default_trans_matrix (parameter/matrix.py:1-17).
    model.transition_matrix = spec.transition_matrix.to_list()

    # climate regime: :57, read at soil_organic_carbon.py:19 as a TRUTHINESS test
    # and at :27 as the coefficient. Per-pixel leaves it None, which is exactly the
    # state climate_regime.py:9-24 leaves the trait in when no regime is chosen.
    if isinstance(spec.climate, FixedClimate):
        model.conversion_coef = spec.climate.coefficient
    elif isinstance(spec.climate, PerPixelClimate):
        model.conversion_coef = None
    else:
        raise TypeError(f"unsupported climate arm: {type(spec.climate).__name__}")

    # land cover source: :60-63 plus the CSV at :54. start_lc/end_lc are read as a
    # truthiness pair at land_cover.py:40 and :58 and at indicator_model.py:184,
    # :194, :205, :214, :232, :247; custom_matrix_file is opened by csv_reader
    # (:315-321) on every one of those property reads, so the file must still
    # exist while the graph is being built.
    if isinstance(spec.land_cover, CustomLandCoverSource):
        model.start_lc = spec.land_cover.start_asset
        model.end_lc = spec.land_cover.end_asset
        if spec.land_cover.scheme is not None:
            model.custom_matrix_file = str(
                write_matrix_csv(spec.land_cover.scheme, workdir / "matrix.csv")
            )
            _verify_custom_matrix_roundtrip(model, spec.land_cover.scheme)
        else:
            # the half-custom arm: two assets and no CSV, so :232 falls back to the
            # run's own transition_matrix and :214 to pm.lc_code.
            model.custom_matrix_file = None
    elif isinstance(spec.land_cover, EsaCciSource):
        model.start_lc = None
        model.end_lc = None
        model.custom_matrix_file = None
    else:
        raise TypeError(f"unsupported land cover arm: {type(spec.land_cover).__name__}")

    # water mask: :66-69, consumed by land_cover.py:56-80. All four are cleared
    # first because the branch chain reads them in order and an arm that left a
    # stale value behind would take an earlier branch than the spec asks for.
    model.water_mask_pixel = None
    model.water_mask_asset_id = None
    model.water_mask_asset_band = None
    model.seasonality = None
    if isinstance(spec.water_mask, PixelValueMask):
        model.water_mask_pixel = spec.water_mask.value
    elif isinstance(spec.water_mask, AssetBandMask):
        model.water_mask_asset_id = spec.water_mask.asset_id
        model.water_mask_asset_band = spec.water_mask.band
    elif isinstance(spec.water_mask, JrcSeasonalityMask):
        model.seasonality = spec.water_mask.threshold
    else:
        raise TypeError(f"unsupported water mask arm: {type(spec.water_mask).__name__}")

    # RunSpec.aoi is `AoiSpec | None`, and an unset one reached `.name` unguarded:
    # it happened to raise from `_feature_collection` first, with "unsupported aoi
    # arm: NoneType", only because Python evaluates arguments left to right. mypy
    # found this the day `tools/` entered its file list. A scenario with no AOI has
    # no legacy run, so refuse it here the way PrecomputedViAsset is refused above.
    if spec.aoi is None:
        raise ValueError("a parity scenario must set an AOI; spec.aoi is None")

    aoi = LegacyAoi(
        feature_collection=_feature_collection(spec.aoi),
        name=spec.aoi.name,
        method=_method(spec.aoi),
    )
    return model, aoi
