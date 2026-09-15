"""sdg1531.spec - the description of a run, as plain data."""

import dataclasses
import json
import pathlib
import subprocess
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

import sdg1531.spec
from sdg1531.enums import Lceu, ProductivityLookup, Trajectory, VegetationIndex
from sdg1531.errors import SpecError
from sdg1531.scheme import LandCoverScheme, TransitionMatrix
from sdg1531.spec import (
    AdminAoi,
    AssetAoi,
    AssetBandMask,
    Compatibility,
    CustomLandCoverSource,
    EsaCciSource,
    FixedClimate,
    GeoJsonAoi,
    JrcSeasonalityMask,
    Period,
    PeriodOverride,
    PerPixelClimate,
    PixelValueMask,
    PrecomputedViAsset,
    RunSpec,
    SensorSelection,
    SubPeriods,
)
from tests.spec_factory import default_spec


def test_period_defaults_to_an_empty_pair():
    assert Period() == Period(start=None, end=None)


def test_period_override_falls_back_to_the_base_period():
    # indicator_model.py:81-93 - `if self.trend_start: ... else: self.start`
    base = Period(start=2000, end=2020)
    assert PeriodOverride().resolve(base) == Period(start=2000, end=2020)


def test_period_override_wins_when_set():
    base = Period(start=2000, end=2020)
    assert PeriodOverride(start=2005).resolve(base) == Period(start=2005, end=2020)
    assert PeriodOverride(end=2015).resolve(base) == Period(start=2000, end=2015)
    assert PeriodOverride(2005, 2015).resolve(base) == Period(start=2005, end=2015)


def test_period_override_uses_truthiness_like_the_legacy_property():
    # indicator_model.py:82 tests `if self.trend_start:` - a falsy 0 falls through.
    base = Period(start=2000, end=2020)
    assert PeriodOverride(start=0).resolve(base) == Period(start=2000, end=2020)


def test_sub_periods_holds_the_overall_period_and_the_five_legacy_overrides():
    # indicator_model.py:16-17 (`start`/`end`) plus the five override pairs at :18-32.
    subs = SubPeriods()
    assert subs.overall == Period()
    assert (subs.trend, subs.state, subs.performance) == (
        PeriodOverride(),
        PeriodOverride(),
        PeriodOverride(),
    )
    assert (subs.land_cover, subs.soc) == (PeriodOverride(), PeriodOverride())


def test_period_types_round_trip_through_dicts():
    subs = SubPeriods(
        overall=Period(2000, 2020),
        trend=PeriodOverride(2001, None),
        soc=PeriodOverride(None, 2019),
    )
    assert SubPeriods.from_dict(subs.to_dict()) == subs
    assert Period.from_dict(Period(1999, 2001).to_dict()) == Period(1999, 2001)


def test_spec_module_does_not_import_ee():
    code = "import sdg1531.spec, sys; assert 'ee' not in sys.modules, sorted(sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# ----------------------------------------------------------------------- unions


def _kind_tags() -> dict[str, str]:
    """Every dataclass DEFINED in ``sdg1531.spec`` (not merely imported into it,
    which is why ``__module__`` is checked) that carries a ``kind: ClassVar[str]``
    tag, keyed by class name. Derived by introspection instead of hand-listed on
    both sides of an assertion: a roster built that way shrinks and grows with
    itself and cannot notice an arm nobody remembered to add to it -- exactly
    the failure this test used to have."""
    return {
        name: obj.kind
        for name, obj in vars(sdg1531.spec).items()
        if dataclasses.is_dataclass(obj)
        and obj.__module__ == sdg1531.spec.__name__
        and isinstance(getattr(obj, "kind", None), str)
    }


def test_every_union_arm_carries_a_stable_kind_tag():
    # A full dict comparison, not `set(tags.values()) == {...}`: the set form
    # collapses two classes sharing one kind into a single element, so a
    # duplicate tag (which would make `_aoi_from_json` and its siblings
    # decode the wrong class) would pass unnoticed. Comparing the whole
    # mapping keeps class and kind paired, and pins the exact count too --
    # no separate floor needed, vacuous or otherwise.
    assert _kind_tags() == {
        "AssetAoi": "asset",
        "GeoJsonAoi": "geojson",
        "AdminAoi": "admin",
        "SensorSelection": "sensors",
        "PrecomputedViAsset": "precomputed_vi",
        "PerPixelClimate": "per_pixel",
        "FixedClimate": "fixed",
        "JrcSeasonalityMask": "jrc_seasonality",
        "PixelValueMask": "pixel_value",
        "AssetBandMask": "asset_band",
        "EsaCciSource": "esa_cci",
        "CustomLandCoverSource": "custom",
    }


def test_per_pixel_climate_token_is_total():
    # indicator_model.py:310 raises TypeError on this default path.
    assert PerPixelClimate().token == "crpix"


def test_fixed_climate_token_transcribes_the_legacy_truncation():
    # indicator_model.py:310 - f"cr{int(self.conversion_coef*100)}" over the five
    # coefficients of parameter/ui.py:41-47. 0.58*100 is 57.99999999999999, so int()
    # truncates to 57; that is the legacy token and it is preserved.
    tokens = [FixedClimate(c).token for c in (0.80, 0.69, 0.58, 0.48, 0.64)]
    assert tokens == ["cr80", "cr69", "cr57", "cr48", "cr64"]


def test_sensor_selection_holds_the_ordered_legacy_sensor_keys():
    # indicator_model.py:35; keys of parameter/sensor.py:14-33.
    source = SensorSelection(names=("Landsat 8", "Landsat 9"))
    assert source.names == ("Landsat 8", "Landsat 9")
    assert SensorSelection().names == ()


def test_water_mask_arms_replace_the_none_comparison_at_land_cover_58():
    assert JrcSeasonalityMask(threshold=8).threshold == 8  # water_mask.py:36-45
    assert PixelValueMask(value=70).value == 70
    assert AssetBandMask(asset_id="users/me/w", band="b1").band == "b1"


def test_custom_land_cover_scheme_is_optional():
    # land_cover.py:40 branches on the two assets alone; indicator_model.py:232 also
    # wants the CSV. Two assets with no CSV keep the default vocabulary.
    source = CustomLandCoverSource(start_asset="users/me/a", end_asset="users/me/b")
    assert source.scheme is None


def test_union_arms_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        AssetAoi(asset_id="users/me/aoi", name="aoi").asset_id = "other"


# ------------------------------------------------------------------- runspec basics


def test_compatibility_defaults_reproduce_the_legacy_behaviour():
    flags = Compatibility()
    assert flags.soc_subsequent_transition_scale == 10  # soil_organic_carbon.py:114
    assert flags.legacy_sensor_folder_token is True  # indicator_model.py:288
    assert flags.derived_vi_msvi_uses_evi_asset is True  # integration.py:66-71
    assert flags.clamp_soc_start_year is False  # soil_organic_carbon.py:12-16


def test_runspec_constructs_with_no_arguments():
    spec = RunSpec()
    assert spec.periods == SubPeriods()
    assert spec.periods.overall == Period()
    assert spec.vi_source is None
    assert spec.aoi is None
    assert spec.compatibility == Compatibility()


def test_runspec_constructs_with_every_optional_field_none():
    # A reactive Solara form builds one field at a time; construction never validates.
    spec = RunSpec(
        periods=SubPeriods(overall=Period(start=None, end=None)),
        vi_source=None,
        threshold=None,
        water_mask=None,
        aoi=None,
    )
    assert spec.vi_source is None
    assert spec.threshold is None
    assert spec.water_mask is None
    assert spec.aoi is None


def test_runspec_defaults_transcribe_the_legacy_trait_defaults():
    spec = RunSpec()
    assert spec.vegetation_index is VegetationIndex.NDVI  # :38
    assert spec.productivity_lookup is ProductivityLookup.GPGV2  # :44
    assert spec.trajectory is Trajectory.NDVI_TREND  # :49
    assert spec.lceu is Lceu.GAES  # :50
    assert spec.transition_matrix == TransitionMatrix.default()  # :53
    assert spec.land_cover == EsaCciSource()
    assert spec.water_mask == JrcSeasonalityMask(threshold=8)
    assert spec.climate == PerPixelClimate()  # climate_regime.py:20-24


def test_runspec_fields_are_the_transcribed_input_traits_in_order():
    # The order is part of the interface: every consumer positionally destructures none
    # of it, but `evolve`/`to_dict` and the goldens below are written against it.
    assert [f.name for f in dataclasses.fields(RunSpec)] == [
        "periods",
        "vi_source",
        "vegetation_index",
        "trajectory",
        "lceu",
        "productivity_lookup",
        "transition_matrix",
        "land_cover",
        "water_mask",
        "climate",
        "aoi",
        "threshold",
        "compatibility",
    ]


def test_dropped_traits_are_absent_from_the_module():
    source = pathlib.Path(sdg1531.spec.__file__).read_text()
    for dropped in ("start_lc_band", "end_lc_band"):
        assert f"{dropped}:" not in source
    assert "lc_pixel_check:" not in source


def test_evolve_returns_a_new_object_and_does_not_mutate():
    spec = RunSpec(periods=SubPeriods(overall=Period(2000, 2020)))
    changed = spec.evolve(periods=SubPeriods(overall=Period(1999, 2020)), lceu=Lceu.AEZ)
    assert changed is not spec
    assert changed.periods.overall == Period(1999, 2020)
    assert changed.lceu is Lceu.AEZ
    assert spec.periods.overall == Period(2000, 2020)
    assert spec.lceu is Lceu.GAES


def test_runspec_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        RunSpec().lceu = Lceu.WTE


# --------------------------------------------------------------- hypothesis strategies

ASSET_IDS = st.text(alphabet="abcdefghijklmnopqrstuvwxyz/_0123456789", min_size=1, max_size=16)
YEARS = st.none() | st.integers(min_value=1980, max_value=2035)
OVERRIDES = st.builds(PeriodOverride, start=YEARS, end=YEARS)

PERIODS = st.builds(Period, start=YEARS, end=YEARS)
SUB_PERIODS = st.builds(
    SubPeriods,
    overall=PERIODS,
    trend=OVERRIDES,
    state=OVERRIDES,
    performance=OVERRIDES,
    land_cover=OVERRIDES,
    soc=OVERRIDES,
)

MATRICES = st.one_of(
    st.just(TransitionMatrix.default()),
    st.builds(
        lambda row, col, value: TransitionMatrix.default().with_cell(row, col, value),
        st.integers(min_value=0, max_value=6),
        st.integers(min_value=0, max_value=6),
        st.sampled_from((-1, 0, 1)),
    ),
)

SCHEMES = st.builds(
    LandCoverScheme,
    start_names=st.lists(ASSET_IDS, min_size=1, max_size=4).map(tuple),
    start_codes=st.lists(st.integers(1, 99), min_size=1, max_size=4).map(tuple),
    end_names=st.lists(ASSET_IDS, min_size=1, max_size=4).map(tuple),
    end_codes=st.lists(st.integers(1, 99), min_size=1, max_size=4).map(tuple),
    matrix=MATRICES,
    is_custom=st.booleans(),
)

RINGS = st.lists(st.lists(st.integers(-180, 180), min_size=2, max_size=2), min_size=3, max_size=5)
AOIS = st.one_of(
    st.builds(AssetAoi, asset_id=ASSET_IDS, name=ASSET_IDS),
    st.builds(
        lambda ring, name: GeoJsonAoi(
            geojson={"type": "Polygon", "coordinates": [ring]}, name=name
        ),
        RINGS,
        ASSET_IDS,
    ),
    st.builds(AdminAoi, admin_code=st.from_regex(r"\A[0-9]{1,6}\Z"), name=ASSET_IDS),
)

VI_SOURCES = st.one_of(
    st.builds(
        SensorSelection,
        names=st.lists(
            st.sampled_from(
                ("Landsat 8", "Landsat 9", "Sentinel 2", "MODIS MOD13Q1", "Derived VI Landsat")
            ),
            # min_size=0: () is the form's initial state (SensorSelection() default), a
            # real shape the round trip must cover, not just the populated cases.
            max_size=3,
        ).map(tuple),
    ),
    st.builds(PrecomputedViAsset, asset_id=ASSET_IDS, scale=st.integers(1, 1000)),
)

CLIMATES = st.one_of(
    st.builds(PerPixelClimate),
    st.builds(
        FixedClimate,
        coefficient=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    ),
)

WATER_MASKS = st.one_of(
    st.builds(JrcSeasonalityMask, threshold=st.integers(1, 12)),
    st.builds(PixelValueMask, value=st.integers(9, 99)),
    st.builds(AssetBandMask, asset_id=ASSET_IDS, band=ASSET_IDS),
)

LAND_COVER_SOURCES = st.one_of(
    st.builds(EsaCciSource),
    st.builds(
        CustomLandCoverSource,
        start_asset=ASSET_IDS,
        end_asset=ASSET_IDS,
        scheme=st.none() | SCHEMES,
    ),
)

COMPATIBILITIES = st.builds(
    Compatibility,
    soc_subsequent_transition_scale=st.sampled_from((10, 100)),
    legacy_sensor_folder_token=st.booleans(),
    derived_vi_msvi_uses_evi_asset=st.booleans(),
    clamp_soc_start_year=st.booleans(),
)

RUN_SPECS = st.builds(
    RunSpec,
    periods=SUB_PERIODS,
    vi_source=st.none() | VI_SOURCES,
    vegetation_index=st.sampled_from(VegetationIndex),
    trajectory=st.sampled_from(Trajectory),
    lceu=st.sampled_from(Lceu),
    productivity_lookup=st.sampled_from(ProductivityLookup),
    transition_matrix=MATRICES,
    land_cover=LAND_COVER_SOURCES,
    water_mask=st.none() | WATER_MASKS,
    climate=CLIMATES,
    aoi=st.none() | AOIS,
    threshold=st.none()
    | st.floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False),
    compatibility=COMPATIBILITIES,
)


# ------------------------------------------------------------------------- round trip


@given(RUN_SPECS)
def test_from_dict_of_to_dict_is_the_identity(spec):
    assert RunSpec.from_dict(spec.to_dict()) == spec


@given(RUN_SPECS)
def test_the_round_trip_survives_real_json(spec):
    payload = json.loads(json.dumps(spec.to_dict()))
    assert RunSpec.from_dict(payload) == spec


def test_a_custom_scheme_keeps_is_custom_through_the_round_trip():
    # is_custom is what LandCoverScheme.palette() and .color_by_class() branch on. A
    # codec that drops it hands stage B of the parity harness a scheme that paints the
    # seven default IPCC colours over a custom vocabulary, and the difference reads as
    # an engine bug rather than a serialization bug.
    scheme = LandCoverScheme(
        start_names=("Native forest", "Other Land"),
        start_codes=(10, 22),
        end_names=("Native forest", "Other Land"),
        end_codes=(10, 22),
        matrix=TransitionMatrix(rows=((0, -1), (1, 0))),
        is_custom=True,
    )
    spec = RunSpec(
        land_cover=CustomLandCoverSource(
            start_asset="users/me/lc_start",
            end_asset="users/me/lc_end",
            scheme=scheme,
        )
    )
    restored = RunSpec.from_dict(json.loads(json.dumps(spec.to_dict())))
    assert restored.land_cover.scheme.is_custom is True
    assert restored == spec


def test_an_admin_aoi_round_trips_through_json():
    spec = default_spec(aoi=AdminAoi(admin_code="185", name="COL"))
    assert RunSpec.from_dict(spec.to_dict()).aoi == AdminAoi(admin_code="185", name="COL")


def test_to_dict_is_json_serializable_for_a_bare_spec():
    assert json.loads(json.dumps(RunSpec().to_dict()))["land_cover"] == {"kind": "esa_cci"}


def test_from_dict_rejects_an_unknown_union_kind():
    payload = RunSpec().to_dict()
    payload["water_mask"] = {"kind": "nope"}
    with pytest.raises(SpecError, match="water_mask: unknown kind 'nope'"):
        RunSpec.from_dict(payload)


def test_from_dict_rejects_a_missing_key():
    payload = RunSpec().to_dict()
    del payload["lceu"]
    with pytest.raises(SpecError, match="missing"):
        RunSpec.from_dict(payload)


def test_from_dict_rejects_an_unknown_enum_value():
    payload = RunSpec().to_dict()
    payload["trajectory"] = "not_a_trend"
    with pytest.raises(SpecError, match="invalid value"):
        RunSpec.from_dict(payload)


# ---------------------------------------------------------- fix round 1: total encoders

# Every union field is typed `X | None` with no constructor validation, so nothing stops
# `RunSpec(aoi="not an aoi")` from being built. Before fix round 1 the five `match`
# encoders had no `case _`, so a value that matched no arm fell off the end and the
# function returned `None` - indistinguishable from the field being genuinely unset. Each
# encoder must instead raise, naming the field and the offending type.


def test_to_dict_rejects_a_wrong_typed_aoi():
    with pytest.raises(SpecError, match="aoi: cannot serialize a str value"):
        RunSpec(aoi="users/me/aoi").to_dict()


def test_to_dict_rejects_a_wrong_typed_vi_source():
    with pytest.raises(SpecError, match="vi_source: cannot serialize a str value"):
        RunSpec(vi_source="landsat").to_dict()


def test_to_dict_rejects_a_wrong_typed_climate():
    with pytest.raises(SpecError, match="climate: cannot serialize a str value"):
        RunSpec(climate="crpix").to_dict()


def test_to_dict_rejects_a_wrong_typed_water_mask():
    with pytest.raises(SpecError, match="water_mask: cannot serialize a str value"):
        RunSpec(water_mask="jrc").to_dict()


def test_to_dict_rejects_a_wrong_typed_land_cover():
    with pytest.raises(SpecError, match="land_cover: cannot serialize a str value"):
        RunSpec(land_cover="esa_cci").to_dict()


def test_fingerprint_no_longer_collides_a_wrong_typed_aoi_with_unset():
    # Before the fix: RunSpec(aoi="users/me/aoi").to_dict()["aoi"] was None, so this
    # spec's fingerprint was identical to RunSpec(aoi=None)'s - two materially different
    # runs sharing one hash. Now both `to_dict` and `fingerprint` raise instead of
    # silently coercing the wrong-typed field to "unset".
    with pytest.raises(SpecError, match="aoi: cannot serialize"):
        RunSpec(aoi="users/me/aoi").fingerprint()
    assert RunSpec(aoi=None).fingerprint() == RunSpec(aoi=None).fingerprint()


# --------------------------------------------------- fix round 1: malformed structure


def test_from_dict_rejects_periods_given_as_a_list():
    payload = RunSpec().to_dict()
    payload["periods"] = []
    with pytest.raises(SpecError, match="malformed"):
        RunSpec.from_dict(payload)


def test_from_dict_rejects_a_null_compatibility():
    payload = RunSpec().to_dict()
    payload["compatibility"] = None
    with pytest.raises(SpecError, match="malformed"):
        RunSpec.from_dict(payload)


def test_from_dict_rejects_a_non_iterable_transition_matrix():
    payload = RunSpec().to_dict()
    payload["transition_matrix"] = 7
    with pytest.raises(SpecError, match="malformed"):
        RunSpec.from_dict(payload)


def test_from_dict_rejects_a_transition_matrix_with_a_null_cell():
    payload = RunSpec().to_dict()
    payload["transition_matrix"] = [[None]]
    with pytest.raises(SpecError, match="malformed"):
        RunSpec.from_dict(payload)


# -------------------------------------------------------------------- fingerprinting

GOLDEN_CANONICAL_JSON = '{"aoi":{"asset_id":"users/me/aoi","kind":"asset","name":"aoi"},"climate":{"coefficient":0.8,"kind":"fixed"},"compatibility":{"clamp_soc_start_year":false,"derived_vi_msvi_uses_evi_asset":true,"legacy_sensor_folder_token":true,"soc_subsequent_transition_scale":10},"land_cover":{"kind":"esa_cci"},"lceu":"gaes","periods":{"land_cover":{"end":null,"start":null},"overall":{"end":2020,"start":2000},"performance":{"end":null,"start":null},"soc":{"end":null,"start":null},"state":{"end":null,"start":null},"trend":{"end":null,"start":2001}},"productivity_lookup":"GPGv2","threshold":0.13,"trajectory":"ndvi_trend","transition_matrix":[[0,-1,-1,-1,-1,-1,0],[1,0,1,-1,-1,-1,0],[1,-1,0,-1,-1,-1,0],[-1,-1,-1,0,-1,-1,0],[1,1,1,1,0,1,0],[1,1,1,1,-1,0,0],[0,0,0,0,0,0,0]],"vegetation_index":"ndvi","vi_source":{"kind":"sensors","names":["Landsat 8","Landsat 9"]},"water_mask":{"kind":"jrc_seasonality","threshold":8}}'

GOLDEN_FINGERPRINT = "54cc478a70658fc2875adc63325cb439d4f255cf9802af45d483d5408cac2f25"


def golden_spec() -> RunSpec:
    return RunSpec(
        periods=SubPeriods(
            overall=Period(start=2000, end=2020),
            trend=PeriodOverride(start=2001, end=None),
        ),
        vi_source=SensorSelection(names=("Landsat 8", "Landsat 9")),
        vegetation_index=VegetationIndex.NDVI,
        trajectory=Trajectory.NDVI_TREND,
        lceu=Lceu.GAES,
        productivity_lookup=ProductivityLookup.GPGV2,
        transition_matrix=TransitionMatrix.default(),
        land_cover=EsaCciSource(),
        water_mask=JrcSeasonalityMask(threshold=8),
        climate=FixedClimate(coefficient=0.80),
        aoi=AssetAoi(asset_id="users/me/aoi", name="aoi"),
        threshold=0.13,
        compatibility=Compatibility(),
    )


def test_canonical_json_golden():
    assert golden_spec().canonical_json() == GOLDEN_CANONICAL_JSON


def test_fingerprint_golden():
    assert golden_spec().fingerprint() == GOLDEN_FINGERPRINT


def test_fingerprint_is_stable_across_round_trips():
    spec = golden_spec()
    assert RunSpec.from_dict(json.loads(json.dumps(spec.to_dict()))).fingerprint() == (
        spec.fingerprint()
    )


def test_fingerprint_changes_when_any_compatibility_flag_changes():
    # The flags are inside the fingerprint - a flipped flag is a different run.
    spec = golden_spec()
    variants = [
        Compatibility(soc_subsequent_transition_scale=100),
        Compatibility(legacy_sensor_folder_token=False),
        Compatibility(derived_vi_msvi_uses_evi_asset=False),
        Compatibility(clamp_soc_start_year=True),
    ]
    digests = {spec.evolve(compatibility=flags).fingerprint() for flags in variants}
    assert spec.fingerprint() not in digests
    assert len(digests) == 4


def test_fingerprint_changes_when_the_transition_matrix_is_edited():
    spec = golden_spec()
    edited = spec.evolve(transition_matrix=spec.transition_matrix.with_cell(0, 1, 1))
    assert edited.fingerprint() != spec.fingerprint()


def test_fingerprint_ignores_field_ordering():
    spec = golden_spec()
    shuffled = dict(reversed(list(spec.to_dict().items())))
    assert RunSpec.from_dict(shuffled).fingerprint() == spec.fingerprint()
