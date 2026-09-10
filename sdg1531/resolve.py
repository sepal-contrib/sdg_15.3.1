"""ResolvedSpec: every derivation of a run, computed once.

Transcribed from the legacy `IndicatorModel` properties and the derivations the
science scripts kept inline (spec §6). This module is the JSON half: it must not
import ee.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from sdg1531.catalog import LAND_COVER_FIRST_YEAR, LAND_COVER_MAX_YEAR, SENSORS
from sdg1531.enums import ProductivityLookup, VegetationIndex
from sdg1531.errors import SpecError
from sdg1531.scheme import LandCoverScheme
from sdg1531.spec import CustomLandCoverSource, Period, PrecomputedViAsset, RunSpec, SensorSelection
from sdg1531.truth_table import PRODUCTIVITY_GPGV1, PRODUCTIVITY_GPGV2, TruthTable

__all__ = [
    "LANDSAT_SENSORS",
    "MODIS_SENSORS",
    "ResolvedSpec",
    "ViAsset",
    "ViProcessor",
    "resolve",
]


def _clamp_cci(year: int) -> int:
    """indicator_model.py:156-168 (and the inline copy at soil_organic_carbon.py:12-14)."""
    return min(max(year, LAND_COVER_FIRST_YEAR), LAND_COVER_MAX_YEAR)


def _require_year(year: int | None, field: str) -> int:
    """Narrow an endpoint to ``int`` before it reaches a CCI clamp.

    Not a legacy transcription: the legacy would raise ``TypeError`` deep inside
    ``max()`` for the same missing-endpoint case. ``RunSpec`` itself never
    validates (``sdg1531.validate`` does, spec §4), so ``resolve()`` is the first
    place that can name what is actually missing.
    """
    if year is None:
        raise SpecError(f"{field} must be set before a run can be resolved")
    return year


def _selected_sensors(spec: RunSpec) -> tuple[str, ...]:
    source = spec.vi_source
    return source.names if isinstance(source, SensorSelection) else ()


def _integration_period(spec: RunSpec) -> Period:
    """integration.py:11-19, duplicated verbatim at :32-40.

    Reads the RAW overrides, not the resolved sub-periods, and never looks at the
    land-cover or SOC sub-periods.
    """
    p = spec.periods
    starts = (p.overall.start, p.trend.start, p.state.start, p.performance.start)
    ends = (p.overall.end, p.trend.end, p.state.end, p.performance.end)
    return Period(
        start=min(v for v in starts if v is not None),
        end=max(v for v in ends if v is not None),
    )


# integration.py:45, :54, :56, :66, :81 — the family sets, verbatim.
MODIS_SENSORS = frozenset({"MODIS MOD13Q1", "MODIS MYD13Q1"})
LANDSAT_SENSORS = frozenset({"Landsat 4", "Landsat 5", "Landsat 7", "Landsat 8", "Landsat 9"})


class ViProcessor(str, Enum):  # noqa: UP042
    """Which rung of integration.py's ladder a sensor selection lands on."""

    MODIS = "modis"
    TERRA_NPP = "terra_npp"
    SENTINEL2 = "sentinel2"
    DERIVED_VI_LANDSAT = "derived_vi_landsat"
    LANDSAT_SENSORS = "landsat_sensors"
    PRECOMPUTED = "precomputed"


# integration.py:41-43 — field 0 of each SENSORS record, so "Derived VI Landsat"
# contributes a (ndvi, evi) pair while every other sensor contributes a bare str. A
# non-derived rung that wins while "Derived VI Landsat" rides along in the same
# selection (e.g. alongside a MODIS sensor) passes that pair through unresolved —
# legacy-faithful (`process_modis` etc. receive the same nested list), not a bug.
type ViAsset = str | tuple[str, str]


def _vi_dispatch(spec: RunSpec) -> tuple[ViProcessor, tuple[ViAsset, ...]]:
    """integration.py:41-94 — an ordered ladder, not a family lookup (spec §6).

    The "GEE Asset" rung (:79-80) is dropped as unreachable; PrecomputedViAsset
    replaces it as a first-class ViSource arm.
    """
    source = spec.vi_source
    if isinstance(source, PrecomputedViAsset):
        return ViProcessor.PRECOMPUTED, (source.asset_id,)
    if not isinstance(source, SensorSelection):
        raise SpecError("vi_source is not set")  # RunSpec allows this while unfilled

    sensors = source.names
    try:
        ee_asset_list: tuple[ViAsset, ...] = tuple(SENSORS[key].collection_id for key in sensors)
    except KeyError as error:
        # An unknown name would otherwise escape as a bare KeyError - the one path out
        # of this module that _require_year's SpecError-naming discipline did not cover.
        raise SpecError(f"{error} is not a known sensor (see sdg1531.catalog.SENSORS)") from error

    if MODIS_SENSORS & set(sensors):  # :45
        return ViProcessor.MODIS, ee_asset_list
    if "Terra NPP" in sensors:  # :54
        return ViProcessor.TERRA_NPP, ee_asset_list
    if "Sentinel 2" in sensors:  # :56
        return ViProcessor.SENTINEL2, ee_asset_list
    if "Derived VI Landsat" in sensors:  # :66
        if (
            spec.vegetation_index is VegetationIndex.MSVI
            and not spec.compatibility.derived_vi_msvi_uses_evi_asset
        ):
            raise SpecError(
                "msvi is served the EVI asset by integration.py:66-71; set "
                "Compatibility.derived_vi_msvi_uses_evi_asset to accept it"
            )
        # :67-71 — indexes ee_asset_list[0], the FIRST SELECTED sensor's asset, not
        # the derived-VI record's. With a Landsat selected first that value is a
        # plain string and this indexes a single character.
        asset_id = (
            ee_asset_list[0][0]
            if spec.vegetation_index is VegetationIndex.NDVI
            else ee_asset_list[0][1]
        )
        return ViProcessor.DERIVED_VI_LANDSAT, (asset_id,)
    if LANDSAT_SENSORS & set(sensors):  # :81
        return ViProcessor.LANDSAT_SENSORS, ee_asset_list
    raise SpecError("No valid sensor type found in the model.")  # :93-94


def _scheme(spec: RunSpec) -> LandCoverScheme:
    """indicator_model.py:183-242 — the custom branch needs both assets AND the CSV.

    Six properties repeat that test today; it is stated once here (spec §7,
    half-custom land cover). A `CustomLandCoverSource` whose CSV has not been
    parsed is half-custom: it falls back to the default vocabulary, carrying the
    run's (possibly edited) transition matrix.

    This picks *which* `LandCoverScheme` the run uses; it never decides whether
    that scheme is custom. `is_custom` is a stored field written once at
    construction — `False` by `LandCoverScheme.default()`, `True` by
    `parse_custom_matrix_csv` (Task 3) — and carried through `RunSpec.to_dict()`
    / `from_dict()` (Task 4). An attached scheme is passed through untouched, so
    `scheme.is_custom` stays the one answer to "did the user supply a CSV" and
    `palette()` / `color_by_class()` cannot disagree with this function.
    """
    source = spec.land_cover
    attached = source.scheme if isinstance(source, CustomLandCoverSource) else None
    if attached is not None:
        return attached
    return LandCoverScheme.default(matrix=spec.transition_matrix)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class ResolvedSpec:
    spec: RunSpec
    analysis_scale: int
    zonal_scale: int
    trend: Period
    state: Period
    performance: Period
    land_cover_period: Period
    soc_period: Period
    integration_period: Period
    lc_year_start_esa: int
    lc_year_end_esa: int
    soc_year_start: int
    soc_year_end_esa: int
    scheme: LandCoverScheme
    lc_class_combinations: tuple[int, ...]
    trans_matrix_flatten: tuple[int, ...]
    lc_palette: tuple[str, ...]
    lc_color_by_class: Mapping[str, str]
    productivity_table: TruthTable
    vi_processor: ViProcessor
    vi_assets: tuple[ViAsset, ...]

    def derived_snapshot(self) -> dict[str, Any]:
        """asdict(self) minus `spec`: the complete, diffable golden-fixture surface."""
        return {
            field.name: _json_safe(getattr(self, field.name))
            for field in fields(self)
            if field.name != "spec"
        }


def resolve(spec: RunSpec) -> ResolvedSpec:
    p = spec.periods
    base = p.overall

    trend = p.trend.resolve(base)  # indicator_model.py:81-94
    state = p.state.resolve(base)  # :96-109
    performance = p.performance.resolve(base)  # :111-124
    land_cover_period = p.land_cover.resolve(base)  # :126-139
    soc_period = p.soc.resolve(base)  # :141-153

    # Dispatched before analysis_scale: an unmatched or empty sensor selection must
    # surface as the ladder's SpecError, not as an IndexError out of SENSORS[sensors[0]].
    vi_processor, vi_assets = _vi_dispatch(spec)

    sensors = _selected_sensors(spec)
    if isinstance(spec.vi_source, PrecomputedViAsset):
        analysis_scale = spec.vi_source.scale
    else:
        analysis_scale = SENSORS[sensors[0]].scale  # indicator_model.py:74-76

    # soil_organic_carbon.py:16 — the start year reaches calendarRange unclamped.
    soc_start = _require_year(soc_period.start, "soc.start")
    soc_year_start = _clamp_cci(soc_start) if spec.compatibility.clamp_soc_start_year else soc_start

    scheme = _scheme(spec)

    return ResolvedSpec(
        spec=spec,
        analysis_scale=analysis_scale,
        zonal_scale=100 if "Sentinel 2" in sensors else 300,  # run_15_3_1.py:324
        trend=trend,
        state=state,
        performance=performance,
        land_cover_period=land_cover_period,
        soc_period=soc_period,
        integration_period=_integration_period(spec),
        lc_year_start_esa=_clamp_cci(_require_year(land_cover_period.start, "land_cover.start")),
        lc_year_end_esa=_clamp_cci(_require_year(land_cover_period.end, "land_cover.end")),
        soc_year_start=soc_year_start,
        # soil_organic_carbon.py:12-14
        soc_year_end_esa=_clamp_cci(_require_year(soc_period.end, "soc.end")),
        scheme=scheme,
        # indicator_model.py:221-227, via LandCoverScheme.class_combinations.
        lc_class_combinations=scheme.class_combinations,
        # :231-242 — the custom CSV matrix, else the (possibly edited) run matrix.
        trans_matrix_flatten=scheme.matrix.flatten(),
        # :244-266 — the seeded sampling and the code-ordered zip live in Task 3.
        lc_palette=scheme.palette(),
        lc_color_by_class=MappingProxyType(scheme.color_by_class()),
        # run_15_3_1.py:184-197
        productivity_table=(
            PRODUCTIVITY_GPGV2
            if spec.productivity_lookup is ProductivityLookup.GPGV2
            else PRODUCTIVITY_GPGV1
        ),
        vi_processor=vi_processor,
        vi_assets=vi_assets,
    )
