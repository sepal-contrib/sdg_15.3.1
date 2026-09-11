"""The description of a run, as plain data.

Transcribed from ``component/model/indicator_model.py`` (the 30 input traits at
:16-70).  This module never imports ``ee`` and never validates: ``RunSpec`` must be
constructible while a reactive Solara form is half filled, so every field has a default
and nothing here raises on construction.  Validation lives in ``sdg1531.validate``.

``start_lc_band`` (:61) and ``end_lc_band`` (:63) are dropped - bound at input_tile.py:209
and :211, read nowhere.  ``lc_pixel_check`` (:70) is not a science parameter; it is the
``exact`` argument to ``check_custom_lc_codes``.

No EXPECTED_DIVERGENCES: the legacy input traits as plain data, with no computation and
no validation. Two traits are dropped -- ``start_lc_band`` and ``end_lc_band``,
bound at input_tile.py:209/:211 and read nowhere -- so dropping them
changes nothing that ran. ``Compatibility``'s flags select between legacy and
corrected behaviour; each flag's effect is recorded by the module it reaches.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar

from sdg1531.enums import Lceu, ProductivityLookup, Trajectory, VegetationIndex
from sdg1531.errors import SpecError
from sdg1531.scheme import LandCoverScheme, TransitionMatrix

__all__ = [
    "AoiSpec",
    "AssetAoi",
    "AssetBandMask",
    "Climate",
    "Compatibility",
    "CustomLandCoverSource",
    "EsaCciSource",
    "FixedClimate",
    "GeoJsonAoi",
    "JrcSeasonalityMask",
    "Json",
    "LandCoverSource",
    "PerPixelClimate",
    "Period",
    "PeriodOverride",
    "PixelValueMask",
    "PrecomputedViAsset",
    "RunSpec",
    "SensorSelection",
    "SubPeriods",
    "ViSource",
    "WaterMaskSpec",
]

type Json = dict[str, Any]


# --------------------------------------------------------------------------- periods


@dataclass(frozen=True, slots=True)
class Period:
    """The assessment period. indicator_model.py:16-17 (``start`` / ``end``)."""

    start: int | None = None
    end: int | None = None

    def to_dict(self) -> Json:
        return {"start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, payload: Json) -> Period:
        return cls(start=payload["start"], end=payload["end"])


@dataclass(frozen=True, slots=True)
class PeriodOverride:
    """An optional sub-period. indicator_model.py:18-32."""

    start: int | None = None
    end: int | None = None

    def resolve(self, base: Period) -> Period:
        # indicator_model.py:81-153 - truthiness, not `is not None`.
        return Period(
            start=self.start if self.start else base.start,
            end=self.end if self.end else base.end,
        )

    def to_dict(self) -> Json:
        return {"start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, payload: Json) -> PeriodOverride:
        return cls(start=payload["start"], end=payload["end"])


@dataclass(frozen=True, slots=True)
class SubPeriods:
    """The assessment period and the five override pairs.

    ``overall`` is indicator_model.py:16-17 (``start`` / ``end``); the five overrides are
    :18-32.  They travel together because every override resolves against ``overall``.
    """

    overall: Period = Period()
    trend: PeriodOverride = PeriodOverride()
    state: PeriodOverride = PeriodOverride()
    performance: PeriodOverride = PeriodOverride()
    land_cover: PeriodOverride = PeriodOverride()
    soc: PeriodOverride = PeriodOverride()

    def to_dict(self) -> Json:
        return {
            "overall": self.overall.to_dict(),
            "trend": self.trend.to_dict(),
            "state": self.state.to_dict(),
            "performance": self.performance.to_dict(),
            "land_cover": self.land_cover.to_dict(),
            "soc": self.soc.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Json) -> SubPeriods:
        return cls(
            overall=Period.from_dict(payload["overall"]),
            trend=PeriodOverride.from_dict(payload["trend"]),
            state=PeriodOverride.from_dict(payload["state"]),
            performance=PeriodOverride.from_dict(payload["performance"]),
            land_cover=PeriodOverride.from_dict(payload["land_cover"]),
            soc=PeriodOverride.from_dict(payload["soc"]),
        )


# ------------------------------------------------------------------------------- aoi


@dataclass(frozen=True, slots=True)
class AssetAoi:
    """An AOI held as a GEE asset id (``AoiView`` method ``ASSET``).

    ``name`` is the label the run carries into asset ids and plots, exactly as
    ``GeoJsonAoi.name`` does - every AOI arm names itself.
    """

    asset_id: str
    name: str
    kind: ClassVar[str] = "asset"


@dataclass(frozen=True, slots=True)
class GeoJsonAoi:
    """An AOI held as geometry (``AoiView`` methods ``ADMIN`` and ``DRAW``)."""

    geojson: Mapping[str, Any]
    name: str
    kind: ClassVar[str] = "geojson"


type AoiSpec = AssetAoi | GeoJsonAoi


# ------------------------------------------------------------------------- vi source


@dataclass(frozen=True, slots=True)
class SensorSelection:
    """indicator_model.py:35 (``sensors``); keys of parameter/sensor.py:14-33."""

    names: tuple[str, ...] = ()
    kind: ClassVar[str] = "sensors"


@dataclass(frozen=True, slots=True)
class PrecomputedViAsset:
    """Replaces the doubly dead "GEE Asset" branch at integration.py:80."""

    asset_id: str
    scale: int
    kind: ClassVar[str] = "precomputed_vi"


type ViSource = SensorSelection | PrecomputedViAsset


# --------------------------------------------------------------------------- climate


@dataclass(frozen=True, slots=True)
class PerPixelClimate:
    """climate_regime.py:9-24 - the default regime, no conversion coefficient."""

    kind: ClassVar[str] = "per_pixel"

    @property
    def token(self) -> str:
        # indicator_model.py:310 raises TypeError here; "crpix" makes run_label total.
        return "crpix"


@dataclass(frozen=True, slots=True)
class FixedClimate:
    """indicator_model.py:57 (``conversion_coef``); parameter/ui.py:41-47.

    Covers both the "predefined" and the "custom" arms of climate_regime.py, which bind
    the same trait (:33-35).
    """

    coefficient: float
    kind: ClassVar[str] = "fixed"

    @property
    def token(self) -> str:
        # indicator_model.py:310 - int() truncation preserved.
        #
        # Known legacy defect, transcribed rather than fixed: phase 1 reproduces the
        # legacy graphs byte for byte, so repairs are phase 2's. Over the slider's
        # real domain (climate_regime.py:29, step=0.01, 101 values) int(c*100)
        # is not injective - float rounding gives only 99 distinct tokens, e.g. 0.28 and
        # 0.29 both truncate to "cr28", 0.56 and 0.57 both to "cr56". folder_name() uses
        # this token as both a directory component and the glob prefix for the
        # "results already exist" check, so two different custom runs can share a
        # result directory and the second silently overwrites the first.
        # fingerprint() still tells them apart - it hashes coefficient, not token.
        return f"cr{int(self.coefficient * 100)}"


type Climate = PerPixelClimate | FixedClimate


# ------------------------------------------------------------------------ water mask


@dataclass(frozen=True, slots=True)
class JrcSeasonalityMask:
    """land_cover.py:74-79.

    No default: the slider's 8 (water_mask.py:36-45) is the form's default, and
    ``RunSpec.water_mask`` supplies it as ``JrcSeasonalityMask(threshold=8)``.
    """

    threshold: int
    kind: ClassVar[str] = "jrc_seasonality"


@dataclass(frozen=True, slots=True)
class PixelValueMask:
    """indicator_model.py:66 (``water_mask_pixel``); land_cover.py:58-67."""

    value: int
    kind: ClassVar[str] = "pixel_value"


@dataclass(frozen=True, slots=True)
class AssetBandMask:
    """indicator_model.py:67-68; land_cover.py:68-73."""

    asset_id: str
    band: str
    kind: ClassVar[str] = "asset_band"


type WaterMaskSpec = JrcSeasonalityMask | PixelValueMask | AssetBandMask


# ------------------------------------------------------------------ land cover source


@dataclass(frozen=True, slots=True)
class EsaCciSource:
    """land_cover.py:44-55 - the CCI collection remapped through translation_matrix."""

    kind: ClassVar[str] = "esa_cci"


@dataclass(frozen=True, slots=True)
class CustomLandCoverSource:
    """indicator_model.py:60-63 (``start_lc``/``end_lc``) + :54 (``custom_matrix_file``).

    ``scheme`` is optional on purpose: land_cover.py:40 takes the custom-asset branch on
    the two assets alone, while indicator_model.py:232 takes the custom-matrix branch
    only with a CSV too.
    """

    start_asset: str
    end_asset: str
    scheme: LandCoverScheme | None = None
    kind: ClassVar[str] = "custom"


type LandCoverSource = EsaCciSource | CustomLandCoverSource


# ---------------------------------------------------------------------- compatibility


@dataclass(frozen=True, slots=True)
class Compatibility:
    """The four flags that select between a legacy defect and its repair.

    Each one names a place where the legacy does something demonstrably wrong; the
    module each flag reaches spells out what that defect is. Every default
    reproduces the legacy behaviour, and the whole record is inside
    ``RunSpec.fingerprint()`` - flipping a flag is a different run.
    """

    soc_subsequent_transition_scale: int = 10  # soil_organic_carbon.py:50 vs :114
    legacy_sensor_folder_token: bool = True  # indicator_model.py:288
    derived_vi_msvi_uses_evi_asset: bool = True  # integration.py:66-71
    clamp_soc_start_year: bool = False  # soil_organic_carbon.py:12-16

    def to_dict(self) -> Json:
        return {
            "soc_subsequent_transition_scale": self.soc_subsequent_transition_scale,
            "legacy_sensor_folder_token": self.legacy_sensor_folder_token,
            "derived_vi_msvi_uses_evi_asset": self.derived_vi_msvi_uses_evi_asset,
            "clamp_soc_start_year": self.clamp_soc_start_year,
        }

    @classmethod
    def from_dict(cls, payload: Json) -> Compatibility:
        return cls(
            soc_subsequent_transition_scale=payload["soc_subsequent_transition_scale"],
            legacy_sensor_folder_token=payload["legacy_sensor_folder_token"],
            derived_vi_msvi_uses_evi_asset=payload["derived_vi_msvi_uses_evi_asset"],
            clamp_soc_start_year=payload["clamp_soc_start_year"],
        )


# -------------------------------------------------------------------------- run spec


@dataclass(frozen=True, slots=True)
class RunSpec:
    """One run, described as data.

    No ``__post_init__``, no constructor validation: a half-filled form must be able to
    build one. Every check lives in ``sdg1531.validate.validate``, which is total.
    """

    periods: SubPeriods = SubPeriods()  # :16-32
    vi_source: ViSource | None = None  # :35
    vegetation_index: VegetationIndex = VegetationIndex.NDVI  # :38
    trajectory: Trajectory = Trajectory.NDVI_TREND  # :49
    lceu: Lceu = Lceu.GAES  # :50
    productivity_lookup: ProductivityLookup = ProductivityLookup.GPGV2  # :44
    transition_matrix: TransitionMatrix = field(default_factory=TransitionMatrix.default)  # :53
    land_cover: LandCoverSource = field(default_factory=EsaCciSource)  # :54, :60-63
    water_mask: WaterMaskSpec | None = field(
        default_factory=lambda: JrcSeasonalityMask(threshold=8)
    )  # :66-69
    climate: Climate = field(default_factory=PerPixelClimate)  # :57
    aoi: AoiSpec | None = None
    threshold: float | None = None  # :41
    compatibility: Compatibility = field(default_factory=Compatibility)

    def evolve(self, **changes: Any) -> RunSpec:
        """Return a copy with ``changes`` applied. The receiver is never mutated."""
        return replace(self, **changes)

    def to_dict(self) -> Json:
        return {
            "periods": self.periods.to_dict(),
            "vi_source": (None if self.vi_source is None else _vi_source_to_json(self.vi_source)),
            "vegetation_index": self.vegetation_index.value,
            "trajectory": self.trajectory.value,
            "lceu": self.lceu.value,
            "productivity_lookup": self.productivity_lookup.value,
            "transition_matrix": _matrix_to_json(self.transition_matrix),
            "land_cover": _land_cover_to_json(self.land_cover),
            "water_mask": (
                None if self.water_mask is None else _water_mask_to_json(self.water_mask)
            ),
            "climate": _climate_to_json(self.climate),
            "aoi": None if self.aoi is None else _aoi_to_json(self.aoi),
            "threshold": self.threshold,
            "compatibility": self.compatibility.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Json) -> RunSpec:
        try:
            return cls(
                periods=SubPeriods.from_dict(payload["periods"]),
                vi_source=(
                    None
                    if payload["vi_source"] is None
                    else _vi_source_from_json(payload["vi_source"])
                ),
                vegetation_index=VegetationIndex(payload["vegetation_index"]),
                trajectory=Trajectory(payload["trajectory"]),
                lceu=Lceu(payload["lceu"]),
                productivity_lookup=ProductivityLookup(payload["productivity_lookup"]),
                transition_matrix=_matrix_from_json(payload["transition_matrix"]),
                land_cover=_land_cover_from_json(payload["land_cover"]),
                water_mask=(
                    None
                    if payload["water_mask"] is None
                    else _water_mask_from_json(payload["water_mask"])
                ),
                climate=_climate_from_json(payload["climate"]),
                aoi=None if payload["aoi"] is None else _aoi_from_json(payload["aoi"]),
                threshold=payload["threshold"],
                compatibility=Compatibility.from_dict(payload["compatibility"]),
            )
        except KeyError as error:
            raise SpecError(f"RunSpec payload is missing {error}") from error
        except TypeError as error:
            # e.g. `periods` given as a list, `compatibility: null`, or a
            # `transition_matrix` that isn't a list of lists of ints - Task 17's parity
            # harness re-reads spec.json off disk, so a corrupt golden must surface as a
            # SpecError with context, not an unannotated TypeError.
            raise SpecError(f"RunSpec payload is malformed: {error}") from error
        except ValueError as error:
            raise SpecError(f"RunSpec payload holds an invalid value: {error}") from error

    def canonical_json(self) -> str:
        """The one serialization ``fingerprint`` hashes: sorted keys, no whitespace."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def fingerprint(self) -> str:
        """A stable content hash of the whole spec, ``Compatibility`` included."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


# ----------------------------------------------------------------- union (de)coding


def _matrix_to_json(matrix: TransitionMatrix) -> list[list[int]]:
    return [list(row) for row in matrix.rows]


def _matrix_from_json(payload: list[list[int]]) -> TransitionMatrix:
    return TransitionMatrix(rows=tuple(tuple(int(v) for v in row) for row in payload))


def _scheme_to_json(scheme: LandCoverScheme) -> Json:
    return {
        "start_names": list(scheme.start_names),
        "start_codes": list(scheme.start_codes),
        "end_names": list(scheme.end_names),
        "end_codes": list(scheme.end_codes),
        "matrix": _matrix_to_json(scheme.matrix),
        "is_custom": scheme.is_custom,
    }


def _scheme_from_json(payload: Json) -> LandCoverScheme:
    return LandCoverScheme(
        start_names=tuple(payload["start_names"]),
        start_codes=tuple(int(c) for c in payload["start_codes"]),
        end_names=tuple(payload["end_names"]),
        end_codes=tuple(int(c) for c in payload["end_codes"]),
        matrix=_matrix_from_json(payload["matrix"]),
        is_custom=bool(payload["is_custom"]),
    )


def _arm(kind: str, **arm_fields: Any) -> Json:
    return {"kind": kind, **arm_fields}


def _kind_of(payload: Json, union: str) -> str:
    if not isinstance(payload, dict) or "kind" not in payload:
        raise SpecError(f"{union}: payload is not a tagged union arm: {payload!r}")
    return str(payload["kind"])


def _aoi_to_json(aoi: AoiSpec) -> Json:
    match aoi:
        case AssetAoi(asset_id=asset_id, name=name):
            return _arm(AssetAoi.kind, asset_id=asset_id, name=name)
        case GeoJsonAoi(geojson=geojson, name=name):
            return _arm(GeoJsonAoi.kind, geojson=dict(geojson), name=name)
        case _:
            raise SpecError(f"aoi: cannot serialize a {type(aoi).__name__} value: {aoi!r}")


def _aoi_from_json(payload: Json) -> AoiSpec:
    kind = _kind_of(payload, "aoi")
    if kind == AssetAoi.kind:
        return AssetAoi(asset_id=payload["asset_id"], name=payload["name"])
    if kind == GeoJsonAoi.kind:
        return GeoJsonAoi(geojson=payload["geojson"], name=payload["name"])
    raise SpecError(f"aoi: unknown kind {kind!r}")


def _vi_source_to_json(source: ViSource) -> Json:
    match source:
        case SensorSelection(names=names):
            return _arm(SensorSelection.kind, names=list(names))
        case PrecomputedViAsset(asset_id=asset_id, scale=scale):
            return _arm(PrecomputedViAsset.kind, asset_id=asset_id, scale=scale)
        case _:
            raise SpecError(
                f"vi_source: cannot serialize a {type(source).__name__} value: {source!r}"
            )


def _vi_source_from_json(payload: Json) -> ViSource:
    kind = _kind_of(payload, "vi_source")
    if kind == SensorSelection.kind:
        return SensorSelection(names=tuple(payload["names"]))
    if kind == PrecomputedViAsset.kind:
        return PrecomputedViAsset(asset_id=payload["asset_id"], scale=int(payload["scale"]))
    raise SpecError(f"vi_source: unknown kind {kind!r}")


def _climate_to_json(climate: Climate) -> Json:
    match climate:
        case PerPixelClimate():
            return _arm(PerPixelClimate.kind)
        case FixedClimate(coefficient=coefficient):
            return _arm(FixedClimate.kind, coefficient=coefficient)
        case _:
            raise SpecError(
                f"climate: cannot serialize a {type(climate).__name__} value: {climate!r}"
            )


def _climate_from_json(payload: Json) -> Climate:
    kind = _kind_of(payload, "climate")
    if kind == PerPixelClimate.kind:
        return PerPixelClimate()
    if kind == FixedClimate.kind:
        return FixedClimate(coefficient=payload["coefficient"])
    raise SpecError(f"climate: unknown kind {kind!r}")


def _water_mask_to_json(mask: WaterMaskSpec) -> Json:
    match mask:
        case JrcSeasonalityMask(threshold=threshold):
            return _arm(JrcSeasonalityMask.kind, threshold=threshold)
        case PixelValueMask(value=value):
            return _arm(PixelValueMask.kind, value=value)
        case AssetBandMask(asset_id=asset_id, band=band):
            return _arm(AssetBandMask.kind, asset_id=asset_id, band=band)
        case _:
            raise SpecError(f"water_mask: cannot serialize a {type(mask).__name__} value: {mask!r}")


def _water_mask_from_json(payload: Json) -> WaterMaskSpec:
    kind = _kind_of(payload, "water_mask")
    if kind == JrcSeasonalityMask.kind:
        return JrcSeasonalityMask(threshold=int(payload["threshold"]))
    if kind == PixelValueMask.kind:
        return PixelValueMask(value=int(payload["value"]))
    if kind == AssetBandMask.kind:
        return AssetBandMask(asset_id=payload["asset_id"], band=payload["band"])
    raise SpecError(f"water_mask: unknown kind {kind!r}")


def _land_cover_to_json(source: LandCoverSource) -> Json:
    match source:
        case EsaCciSource():
            return _arm(EsaCciSource.kind)
        case CustomLandCoverSource(start_asset=start_asset, end_asset=end_asset, scheme=scheme):
            return _arm(
                CustomLandCoverSource.kind,
                start_asset=start_asset,
                end_asset=end_asset,
                scheme=None if scheme is None else _scheme_to_json(scheme),
            )
        case _:
            raise SpecError(
                f"land_cover: cannot serialize a {type(source).__name__} value: {source!r}"
            )


def _land_cover_from_json(payload: Json) -> LandCoverSource:
    kind = _kind_of(payload, "land_cover")
    if kind == EsaCciSource.kind:
        return EsaCciSource()
    if kind == CustomLandCoverSource.kind:
        scheme = payload["scheme"]
        return CustomLandCoverSource(
            start_asset=payload["start_asset"],
            end_asset=payload["end_asset"],
            scheme=None if scheme is None else _scheme_from_json(scheme),
        )
    raise SpecError(f"land_cover: unknown kind {kind!r}")
