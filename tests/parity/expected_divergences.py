"""The deliberate divergences from D9's byte-parity rule.

**An entry here is a LICENCE TO DIFFER, and a licence is only ever as narrow as
its patterns.** ``EXPECTED_DIVERGENCES`` is keyed on (scenario glob, layer glob),
and a glob that covers a whole layer licenses everything in that layer: every node,
every argument, every ordering. This register carried exactly such an entry --
``("*", "indicator_15_3_1")``, written for the band rename below -- and under it
the 30-rule collapse, its rule order, the water mask and the cast position of the
module's headline output were compared against nothing at all. Swapping
``.uint8()`` and ``.where(water, 0)`` in ``build_indicator`` left all 101 parity
tests green. Before adding an entry, ask what a mutation INSIDE the region it
covers would do; if the answer is "nothing", the entry is too broad.

**A licence is the LAST resort, not the first.** Every register below except the
first says a true, narrow thing about the shape of the difference; only the first
says "these may differ" and stops looking. The order here is the order to try:

``EXPECTED_NORMALISATIONS``
    a graph pair that differs by a known node, which the harness SPLICES OUT and
    then requires byte equality on the remainder. Strictly stronger than a licence,
    and where a difference belongs whenever it can be described structurally: the
    normalisation is written down as code, tested for what it refuses as well as
    what it removes, and it leaves the rest of the layer compared.
``EXPECTED_LEGACY_ONLY_FAILS`` / ``EXPECTED_LEGACY_AND_PORT_BOTH_FAIL``
    scenarios with no graph pair at all, because one tree or both refused to build
    one. Sets of scenario names, each consulted only by the branch it applies to.
    Not licences: nothing is exempted from a comparison, because there is nothing
    to compare.
``EXPECTED_COMPATIBILITY_DIVERGENCES``
    the layers a non-default :class:`~sdg1531.spec.Compatibility` moves. Not a
    licence either, and the harness does NOT grant one: see below.
``EXPECTED_OFF_GRAPH``
    real divergences that produce no graph pair in this corpus, so the
    both-directions rule cannot police them. Each names the tests that do.
``HELD_CONSTANT``
    inputs both trees are built from identically, so no mutation of them can make
    a comparison fail. Nothing diverges; they are here because this file is where
    a reader looks to learn what the harness does not compare.
``EXPECTED_DIVERGENCES``
    a GRAPH PAIR that differs and is licensed outright. Currently EMPTY, which is
    the strongest statement this file can make. Keys are (scenario glob, layer
    glob) and the table fails in both directions -- an unlisted divergence fails, a
    listed one that no longer appears fails, an entry matching nothing fails. None
    of that keeps an entry NARROW, and nothing can except reading it.

Every entry cites the numbered ``EXPECTED_DIVERGENCES`` note in the port module
that declares it, and ``MODULE_NOTE_CLAIMS`` below maps every such note to the
register entry that accounts for it. ``tests/parity/test_parity.py`` checks that
mapping in both directions against the notes :func:`note_modules` FINDS by scanning
``sdg1531/``, so a new module note cannot appear without a register entry and a
register entry cannot cite a note that no longer exists. The scan is the point: the
roster used to be a hand-written tuple of seven files, and the three modules
missing from it had sixteen declared divergences between them that never reached
the register -- with the both-directions test green the whole time, because it
checked the roster against itself.
"""

from __future__ import annotations

import ast
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import NotRequired, TypedDict


class Normalisation(TypedDict):
    """One EXPECTED_NORMALISATIONS entry.

    ``splice`` names the function in ``tests/parity/canonical.py`` that performs
    the edit; ``tests`` names EVERY test that pins it, because an entry citing one
    test for a two-part claim reads as coverage it does not have.
    """

    note: str
    splice: str
    reason: str
    tests: tuple[str, ...]


class OffGraph(TypedDict):
    """One EXPECTED_OFF_GRAPH entry.

    ``note`` is NotRequired because two divergences come from modules that carry no
    numbered note at all -- ``resolve.py`` and the unported ``component/tile/`` --
    and ``MODULE_NOTE_CLAIMS`` cannot reference what does not exist.
    """

    reason: str
    tests: tuple[str, ...]
    note: NotRequired[str]


__all__ = [
    "EXPECTED_COMPATIBILITY_DIVERGENCES",
    "EXPECTED_DIVERGENCES",
    "EXPECTED_LEGACY_AND_PORT_BOTH_FAIL",
    "EXPECTED_LEGACY_ONLY_FAILS",
    "EXPECTED_NORMALISATIONS",
    "EXPECTED_OFF_GRAPH",
    "GRAPH_DIVERGENCE_NOTES",
    "HELD_CONSTANT",
    "LEGACY_ONLY_FAILS_NOTE",
    "MODULE_NOTE_CLAIMS",
    "Normalisation",
    "OffGraph",
    "matching_entry",
    "module_notes",
    "note_modules",
]

# Layers that are allowed to DIFFER. Empty, and that is the strongest thing this
# file can say: all 112 graph pairs are compared byte for byte after
# canonicalisation, with no exemption anywhere. The machinery stays because a real
# licence may one day be justified -- but adding one is a decision, not a fix, and
# `test_no_layer_is_licensed` is where a reviewer is told it was taken.
#
# It held two kinds of entry before. `("*", "indicator_15_3_1")` licensed the whole
# indicator layer for the sake of one renamed band, and is now
# EXPECTED_NORMALISATIONS. Nine `("sNN", "*")` entries licensed whole scenarios for
# the sake of "the legacy crashed here", and are now EXPECTED_LEGACY_ONLY_FAILS.
# Both were written narrow and read wide; that is what a glob does.
EXPECTED_DIVERGENCES: dict[tuple[str, str], str] = {}

# Which module note licenses each graph entry above. Separate from the reason
# strings because `matching_entry` returns those verbatim to a failing assertion.
GRAPH_DIVERGENCE_NOTES: dict[tuple[str, str], str] = {}

# Scenarios the LEGACY refuses and the port builds: a CUSTOM land cover source with
# a JRC or asset-band mask. land_cover.py:58 reads
#     if model.start_lc and model.end_lc and model.water_mask_pixel > 9:
# so water_mask_pixel is None and the legacy raises TypeError before it builds
# anything at all. The port's three-arm union removes the comparison. Exactly the
# _TABLE rows with land_cover in {custom_full, custom_half} AND water in {jrc,
# asset_band}; rows with a custom source and a PIXEL mask (s06, s07, s10, s11, s19,
# s21, s25, s27) are deliberately absent, because 70 > 9 and 10 > 9 are both true,
# the legacy takes branch 1, and the port emits the same graph.
#
# A frozenset, consulted only by the error.json branch, and NOT nine
# ("sNN", "*") entries in EXPECTED_DIVERGENCES, which is how they were spelled
# until fix round 1. Those were correct -- stage A recorded no layer files for
# these scenarios, so there was no pair to compare -- but what they SAID was "every
# layer of this scenario may differ arbitrarily". The two readings coincided only
# because `dump_scenario` rmtree's a scenario directory before writing, so a
# scenario never holds both error.json and layer graphs. Re-run stage A after a
# legacy change that stops one of these crashing -- which the harness itself tells
# you to do -- and seven real layers would have become wholesale-licensed with
# every register test still green, because `matching_entry("s05", "land_cover")`
# matches the "*" glob whichever branch ran. A set of scenario names cannot decay
# into a graph licence.
EXPECTED_LEGACY_ONLY_FAILS: frozenset[str] = frozenset(
    {"s05", "s08", "s09", "s12", "s17", "s18", "s20", "s26", "s28"}
)

# engine/land_cover.py note 4 is what declares the divergence above.
LEGACY_ONLY_FAILS_NOTE = "sdg1531/engine/land_cover.py:4"

# Differences the harness SPLICES OUT before comparing, rather than licensing.
#
# The distinction is the whole lesson of this register. A licence says "this layer
# may differ" and stops looking; a normalisation says "these exact nodes differ,
# here is the code that removes them, and everything else must still be equal
# byte for byte". Anything describable as a structural edit belongs here.
#
# Each entry names the function in `tests/parity/canonical.py` that performs it and
# a test that pins it. The tests that matter are the ones about what the splice
# REFUSES: `test_the_splice_declines_on_the_legacy_graph` (it is asymmetric, so it
# cannot cancel the same node on both sides and compare nothing) and
# `test_the_splice_declines_when_the_cast_moves_inside_the_water_mask` (it is tied
# to one position, so a port that moved the cast is not normalised, it fails).
EXPECTED_NORMALISATIONS: dict[str, Normalisation] = {
    # --- engine/indicator.py ---------------------------------------------------
    "indicator_band_rename": {
        "note": "sdg1531/engine/indicator.py:1",
        "splice": "strip_indicator_band_rename",
        "reason": (
            "build_indicator ends `.rename('indicator_15_3_1')`, where "
            "run_15_3_1.py:411 returns ee.Image(0).where(...).uint8() with no "
            "rename at all, so the legacy band is literally called 'constant' "
            "(spec 7). One extra Image.rename node, in one position, in every "
            "scenario's indicator layer. It was originally licensed as "
            "('*', 'indicator_15_3_1'), which licensed the entire indicator graph "
            "-- the 30-rule collapse, its rule order, the water mask and the cast "
            "position all went uncompared. Splicing the node out instead leaves "
            "the rest of the layer under the ordinary byte-equality rule."
        ),
        "tests": ("test_the_splice_turns_the_port_graph_into_the_legacy_one",),
    },
}

# Scenarios BOTH trees refuse. There is no graph pair, so these are not
# divergences and must not be listed above: ESA CCI plus a pixel mask that is not
# the IPCC water code 70. The legacy falls past every branch of
# land_cover.py:56-80 to int(model.seasonality) with that trait still None and
# raises TypeError; the port raises SpecError from build_water_mask. Exactly
# the _TABLE rows with land_cover == "esa" and water == "pixel_10".
EXPECTED_LEGACY_AND_PORT_BOTH_FAIL: frozenset[str] = frozenset({"s03", "s15", "s24"})

# The layers each scenario's non-default Compatibility moves, scenario -> layer
# stems. Absent means "the flags this scenario sets change nothing".
#
# These are NOT divergences and are NOT licensed. `Compatibility`'s DEFAULTS are
# the legacy behaviour by construction (spec.py), so a spec that flips a flag
# describes a run the legacy cannot express and has no golden to be compared
# against. Stage B therefore compares the port built with `Compatibility()`, which
# must match the goldens under the ordinary rule with no exemption at all -- a
# transcription bug cannot hide behind a flag. This table is the separate,
# both-directions statement of what the flags actually do, so an inert flag (or a
# flag that suddenly moves a layer it never moved) fails.
#
# Only two of the four flags reach a graph. `legacy_sensor_folder_token` feeds
# `naming.run_label` and `derived_vi_msvi_uses_evi_asset` only turns a preserved
# defect into a raise; neither is varied by the corpus.
#
# The corpus rows that set a flag and appear nowhere below are inert, for reasons
# that are properties of their periods rather than of the flags:
#   s08, s27  soc_subsequent_transition_scale, but the SOC period holds a single
#             year pair (soil_organic_carbon.py:95's range is empty), so there is
#             no "subsequent" transition to rescale.
#   s09, s18, s28  clamp_soc_start_year, but the SOC start is already at or after
#             LAND_COVER_FIRST_YEAR, so the clamp is the identity.
#   s03, s15, s24  refused by both trees before any graph is built.
EXPECTED_COMPATIBILITY_DIVERGENCES: dict[str, frozenset[str]] = {
    # soc_subsequent_transition_scale=100 -- soil_organic_carbon.py:114's
    # multiply(10) becomes multiply(100) for every year pair after the first (D13).
    "s02": frozenset({"soc", "indicator_15_3_1"}),
    "s05": frozenset({"soc", "indicator_15_3_1"}),
    "s11": frozenset({"soc", "indicator_15_3_1"}),
    "s14": frozenset({"soc", "indicator_15_3_1"}),
    "s17": frozenset({"soc", "indicator_15_3_1"}),
    "s21": frozenset({"soc", "indicator_15_3_1"}),
    # clamp_soc_start_year=True -- the SOC start year reaches calendarRange clamped
    # to the CCI range, where soil_organic_carbon.py:16 passes it through raw.
    "s06": frozenset({"soc", "indicator_15_3_1"}),
    "s12": frozenset({"soc", "indicator_15_3_1"}),
    "s22": frozenset({"soc", "indicator_15_3_1"}),
    "s25": frozenset({"soc", "indicator_15_3_1"}),
}

# Inputs the harness HOLDS CONSTANT, so no mutation of them can make a comparison
# fail. Not divergences -- nothing differs -- but this file is the document a
# reader consults to learn what the harness does not compare, and something
# excluded from every comparison belongs in it just as much as something licensed.
HELD_CONSTANT: dict[str, OffGraph] = {
    "aoi_leaf": {
        "reason": (
            "tools/to_legacy_model.py's _feature_collection is a deliberate, "
            "documented copy of ExecutionContext.from_aoi_spec "
            "(sdg1531/engine/context.py:48-57): both spell an AssetAoi as "
            "ee.FeatureCollection(asset_id) and a GeoJsonAoi as "
            "ee.FeatureCollection(geojson). The reasoning is sound -- the AOI is an "
            "INPUT to both trees rather than a thing under test, and in the real "
            "legacy it came from sepal_ui's AoiModel, not from a RunSpec -- but the "
            "consequence is that the AOI is the one node in every golden that came "
            "from the port. A mutation of it changes both sides identically and no "
            "parity test can fail. The tests below pin the port's spelling; the "
            "adapter's is a reviewed copy and stage B cannot import it to check "
            "(tools/to_legacy_model.py imports the legacy tree)."
        ),
        "tests": (
            "test_from_aoi_spec_asset_arm",
            "test_from_aoi_spec_geojson_arm",
        ),
    },
}

# Divergences that are real but produce no graph pair to compare, so the
# both-directions rule cannot police them. Each names the test that does.
EXPECTED_OFF_GRAPH: dict[str, OffGraph] = {
    # --- engine/integration.py ------------------------------------------------
    "vi_threshold_narrowing": {
        "note": "sdg1531/engine/integration.py:1",
        "reason": (
            "require_float raises SpecError for an unset spec.threshold where "
            "vi_threshold (integration.py:410-415) built an Image.gt node with its "
            "image2 argument absent. Every corpus row sets a threshold, so the "
            "harness never reaches it."
        ),
        "tests": ("test_an_unset_threshold_raises_on_every_rung_that_consumes_it",),
    },
    # --- engine/land_cover.py -------------------------------------------------
    "esa_pixel_mask_not_water": {
        "note": "sdg1531/engine/land_cover.py:1",
        "reason": (
            "a PixelValueMask over EsaCciSource whose value is not 70 raises "
            "SpecError. In the corpus this is s03/s15/s24, which the legacy also "
            "refuses -- see EXPECTED_LEGACY_AND_PORT_BOTH_FAIL -- so there is no "
            "graph pair either way."
        ),
        "tests": ("test_a_pixel_value_mask_over_esa_cci_rejects_a_non_water_code",),
    },
    "unset_water_mask": {
        "note": "sdg1531/engine/land_cover.py:2",
        "reason": (
            "an unset spec.water_mask raises SpecError where land_cover.py:74-81 "
            "built a JRC mask from model.seasonality. RunSpec allows None; the "
            "corpus never uses it, because a scenario with no mask has no graph."
        ),
        "tests": ("test_an_unset_water_mask_is_rejected",),
    },
    "unrecognised_arm": {
        "note": "sdg1531/engine/land_cover.py:3",
        "reason": (
            "an unrecognised land cover or water mask arm raises SpecError. Both "
            "are closed unions, so no RunSpec the corpus can build reaches it. TWO "
            "tests, because the claim has two halves: the entry cited only the "
            "water-mask one, and land_cover.py:151 -- the source arm -- was reached "
            "by nothing in the suite."
        ),
        "tests": (
            "test_an_unset_water_mask_is_rejected",
            "test_an_unrecognised_land_cover_source_is_rejected",
        ),
    },
    # --- engine/productivity.py -----------------------------------------------
    "unresolved_period_bound": {
        "note": "sdg1531/engine/productivity.py:1",
        "reason": (
            "require_int raises SpecError for an unset trend/state/performance "
            "bound where productivity.py:120-122 and :196-199 handed None to "
            "ee.Filter and to arithmetic. Every corpus row resolves all three, and "
            "so does the citation -- naming only the trend test left state and "
            "performance reading as covered when they were not."
        ),
        "tests": (
            "test_build_trajectory_requires_a_resolved_trend",
            "test_build_state_requires_a_resolved_state_period",
            "test_build_performance_requires_a_resolved_performance_period",
        ),
    },
    "unknown_lceu": {
        "note": "sdg1531/engine/productivity.py:2",
        "reason": (
            "an unknown Lceu raises SpecError where productivity.py:92-116 fell "
            "through to UnboundLocalError. Lceu is closed; the corpus covers all "
            "five members."
        ),
        "tests": ("test_unknown_lceu_raises_a_spec_error",),
    },
    "unknown_trajectory": {
        "note": "sdg1531/engine/productivity.py:3",
        "reason": (
            "an unknown Trajectory raises SpecError where productivity.py:30-51 "
            "left z_score unbound. Trajectory is closed."
        ),
        "tests": ("test_unknown_trajectory_raises_a_spec_error",),
    },
    "s_res_trend_unavailable": {
        "note": "sdg1531/engine/productivity.py:4",
        "reason": (
            "S_RES_TREND raises SpecError where productivity.py:41-43 raised a bare "
            "NameError. It is excluded from the corpus for exactly that reason: it "
            "has no legacy graph to compare against."
        ),
        "tests": ("test_s_res_trend_raises_a_spec_error_not_a_name_error",),
    },
    # --- engine/soc.py --------------------------------------------------------
    "unrecognised_climate_arm": {
        "note": "sdg1531/engine/soc.py:1",
        "reason": (
            "an unrecognised spec.climate arm raises SpecError; the legacy if/else "
            "at soil_organic_carbon.py:19-27 is total, so there is no arm to "
            "compare and no RunSpec that reaches this."
        ),
        "tests": ("test_an_unsupported_climate_regime_raises_spec_error",),
    },
    "zero_climate_coefficient": {
        "note": "sdg1531/engine/soc.py:2",
        "reason": (
            "FixedClimate(coefficient=0.0) takes the fixed branch and builds "
            "ee.Image(1).divide(0.0), where soil_organic_carbon.py:19's truthiness "
            "test sent it to the per-pixel IPCC remap -- a different graph. None of "
            "the five UI coefficients is 0.0, so the corpus cannot reach it."
        ),
        "tests": (
            "test_a_zero_coefficient_takes_the_fixed_branch_where_the_legacy_took_per_pixel",
        ),
    },
    # --- engine/indicator.py --------------------------------------------------
    "dropped_year_order_guard": {
        "note": "sdg1531/engine/indicator.py:2",
        "reason": (
            "build_indicator_maps drops run_15_3_1.py:165-167's "
            "`if not (model.start < model.end): raise`; the check moved to "
            "sdg1531.validate. Every corpus window has start < end, so no scenario "
            "distinguishes the two."
        ),
        "tests": ("test_start_not_before_end_is_fatal",),
    },
    "layers_is_total": {
        "note": "sdg1531/engine/indicator.py:3",
        "reason": (
            "IndicatorMaps.layers() is a total mapping over the seven "
            "IndicatorLayer members where indicator_n_category_label "
            "(run_15_3_1.py:427-448) had no else and raised UnboundLocalError. "
            "That is a Python-level shape, not a graph node."
        ),
        "tests": ("test_layers_returns_exactly_seven_entries_in_spec_order",),
    },
    "trend_and_state_export_vocabulary": {
        "note": "sdg1531/engine/indicator.py:4",
        "reason": (
            "the trend and state layers get a 3-class export band and legend for "
            "the first time; display_maps (run_15_3_1.py:105-158) never drew them. "
            "The STATISTICS vocabulary is unchanged -- _STATS_BAND keeps "
            "trajectory_5_levels / state_5_levels and _STATS_LABELS keeps the "
            "six-entry legends -- which is what stops this note from licensing a "
            "statistics regression."
        ),
        "tests": (
            "test_the_statistics_vocabulary_deliberately_differs_from_the_export_vocabulary",
        ),
    },
    # --- stats/requests.py ----------------------------------------------------
    "stats_transport": {
        "note": "sdg1531/stats/requests.py:1",
        "reason": (
            "run_15_3_1.py:237-239 and :285-287 pulled the two area tables over "
            "getDownloadURL + urlopen; they now go through get_info_async on the "
            "same ee.Dictionary. A getDownloadURL graph is not a getInfo graph. "
            "The entry licenses the two wrapper nodes and the endpoint and nothing "
            "else -- no reducer, band, scale or numeric difference."
        ),
        "tests": ("test_the_two_area_reducers_keep_the_legacy_constant_types",),
    },
    # --- stats/decode.py ------------------------------------------------------
    "zonal_error_reporting": {
        "note": "sdg1531/stats/decode.py:1",
        "reason": (
            "decode_zonal_areas raises a chained StatisticsError and prints nothing "
            "where zonal_statistics_to_geodataframe (run_15_3_1.py:475-569) printed "
            "and returned None, and it rejects {'features': []}, which the legacy "
            "decoded to an empty frame. Payload decoding, not a graph."
        ),
        "tests": ("test_empty_payload_raises_statistics_error",),
    },
    "distinct_pixel_values_sorted": {
        "note": "sdg1531/stats/decode.py:2",
        "reason": (
            "decode_distinct_pixel_values sorts; custom_lc_values "
            "(run_15_3_1.py:421-422) returned histogram key order. Same integers, "
            "same count, different order."
        ),
        "tests": ("test_decode_distinct_pixel_values_returns_sorted_ints",),
    },
    "transition_label_split": {
        "note": "sdg1531/stats/decode.py:3",
        "reason": (
            "run_15_3_1.py:241's bare zip truncated a scheme whose code and name "
            "lists disagree in length, silently mislabelling the table; "
            "decode_transition_areas zips strict=True and raises. run_15_3_1.py:243 "
            "also joined the class names into one 'start_end' string and split it "
            "back on '_', which yields more than three columns for any class name "
            "containing an underscore."
        ),
        "tests": ("test_decode_transition_areas_rejects_a_malformed_scheme",),
    },
    "areas_by_land_cover_column_name": {
        "note": "sdg1531/stats/decode.py:4",
        "reason": (
            "the class column is layer.value (the snake id) where "
            "run_15_3_1.py:297 used the translated indicator_name. No value, row or "
            "ordering differs -- display strings are the app layer's."
        ),
        "tests": (
            "test_decode_areas_by_land_cover_uses_the_five_class_labels_for_productivity_state",
        ),
    },
    # --- export.py --------------------------------------------------------------
    # None of these five reaches an `ee` graph: `zonal_shapefile_zip` runs on a
    # decoded GeoDataFrame, downstream of every request. They went unaccounted for
    # a whole round because NOTE_MODULES was a hand-written roster and export.py
    # was not on it -- see `note_modules`.
    "shapefile_zip_returns_bytes": {
        "note": "sdg1531/export.py:1",
        "reason": (
            "zonal_shapefile_zip writes into a TemporaryDirectory that is gone "
            "before it returns and hands the caller bytes, where run_15_3_1.py:"
            "356-366 wrote the five members into ~/module_results and left them "
            "beside the zip. Where the zip lands is the app layer's decision (D12)."
        ),
        "tests": (
            "test_it_leaves_nothing_behind_in_the_working_directory",
            "test_it_deletes_the_temporary_directory_it_wrote_into",
            "test_the_zip_round_trips_back_into_geopandas",
        ),
    },
    "shapefile_zip_member_set_and_compression": {
        "note": "sdg1531/export.py:2",
        "reason": (
            "the archive holds exactly the members the driver wrote, sorted by "
            "name, and is ZIP_DEFLATED; run_15_3_1.py:359 zipped a hard-coded "
            "suffix list in its own order and :361 took ZipFile's ZIP_STORED "
            "default. The bytes differ, the members inside do not."
        ),
        "tests": (
            "test_zip_contains_every_mandatory_shapefile_member",
            "test_the_zip_is_deflated_not_stored",
        ),
    },
    "shapefile_zip_member_stem": {
        "note": "sdg1531/export.py:3",
        "reason": (
            "members are named zonal.*, where run_15_3_1.py:356 used the "
            "run-specific indicator_stats stem. Invisible to geopandas, which "
            "resolves the single .shp either way; visible to a user who unzips it."
        ),
        "tests": ("test_zip_contains_every_mandatory_shapefile_member",),
    },
    "shapefile_zip_empty_frame": {
        "note": "sdg1531/export.py:4",
        "reason": (
            "an empty or absent frame raises StatisticsError. decode_zonal_areas "
            "rejects an empty payload but then drops LineString zones without "
            "re-checking (stats/decode.py:269), so an all-LineString AOI still "
            "arrives with nothing in it; the legacy handed that to to_file and "
            "shipped a zero-feature shapefile."
        ),
        "tests": (
            "test_an_empty_frame_raises_a_domain_error",
            "test_a_missing_frame_raises_the_same_domain_error",
        ),
    },
    "shapefile_zip_driver_error": {
        "note": "sdg1531/export.py:5",
        "reason": (
            "a driver failure is re-raised as a StatisticsError chaining the "
            "original, where at run_15_3_1.py:356 the driver's own exception "
            "escaped uncaught. On input the legacy wrote successfully the two "
            "produce the same five members."
        ),
        "tests": (
            "test_a_driver_failure_is_reported_as_a_domain_error",
            "test_a_writer_that_produced_no_members_is_reported_as_a_domain_error",
        ),
    },
    # --- stats/api.py -----------------------------------------------------------
    # Request ORCHESTRATION, not graph shape: the graphs these functions await are
    # stats/requests.py's, which the harness compares. Nothing here is a node.
    "zonal_feature_count_guard": {
        "note": "sdg1531/stats/api.py:1",
        "reason": (
            "fetch_zonal_areas refuses a zone collection of more than 5000 "
            "features; zonal_statistics_to_geodataframe only remarked on the limit "
            "in a comment (run_15_3_1.py:542) and fetched anyway. The entry is "
            "exactly that threshold -- at or below 5000 nothing changes -- plus the "
            "one extra round trip the size probe costs."
        ),
        "tests": (
            "test_fetch_zonal_areas_guards_the_feature_count",
            "test_fetch_zonal_areas_accepts_a_collection_at_the_limit",
        ),
    },
    "band_names_keep_ee_order": {
        "note": "sdg1531/stats/api.py:2",
        "reason": (
            "fetch_band_names returns Earth Engine's own band order where "
            "widget/select_lc.py:63-65 natsorted it first. Display ordering is the "
            "app layer's (spec 4), so the sort moves rather than disappears. Covers "
            "the ORDER of this one function's result and nothing else."
        ),
        "tests": ("test_fetch_band_names_keeps_earth_engines_own_order",),
    },
    "batched_fetch_error_chaining": {
        "note": "sdg1531/stats/api.py:3",
        "reason": (
            "_unwrap raises a chained StatisticsError for an Exception that arrived "
            "as a value. The legacy had no batching fetcher at all -- every call was "
            "a blocking getInfo or urlopen -- so there is nothing to compare."
        ),
        "tests": (
            "test_an_exception_payload_is_chained_not_swallowed",
            "test_a_raised_fetcher_error_reaches_the_caller_unchanged",
        ),
    },
    # --- stats/plots.py ---------------------------------------------------------
    # The charts are the furthest thing from an `ee` graph in the port: the legacy
    # drew matplotlib figures, these return option dicts. Every entry below is
    # about numbers or labels in a dict, never a node.
    "charts_return_options_not_figures": {
        "note": "sdg1531/stats/plots.py:1",
        "reason": (
            "sankey.py:42/:235 and bar_plot.py:11/:26 returned a matplotlib "
            "(fig, ax); these return option dicts and never draw. Everything purely "
            "visual therefore has no counterpart -- geometry, the 2% gap, the 0.65 "
            "ribbon alpha, the year watermarks, bold titles, hidden spines, legend "
            "placement. The numbers behind them are unchanged."
        ),
        "tests": (
            "test_sankey_is_one_series_declared_as_a_sankey",
            "test_distribution_axes_are_wired_for_a_horizontal_bar_chart",
        ),
    },
    "sankey_node_names_carry_the_year": {
        "note": "sdg1531/stats/plots.py:2",
        "reason": (
            "node names carry the year ('Cropland 2001'); sankey.py:66-70 drew two "
            "independent columns and could repeat a bare label across them. ECharts "
            "identifies nodes by name and forbids a repeat, so without the suffix an "
            "unchanged class collapses into one self-looping node. Label text only."
        ),
        "tests": (
            "test_sankey_nodes_carry_the_year_so_echarts_cannot_merge_them",
            "test_sankey_has_no_self_loop_for_an_unchanged_class",
            "test_sankey_node_names_are_never_repeated",
        ),
    },
    "chart_row_order_follows_the_vocabulary": {
        "note": "sdg1531/stats/plots.py:3",
        "reason": (
            "sankey columns and distribution rows follow the scheme vocabulary; "
            "sankey.py:66-70 used the frame's first-appearance order and "
            "bar_plot.py the pivot's alphabetical index. Same members, same values, "
            "different drawing order."
        ),
        "tests": (
            "test_sankey_orders_its_columns_by_the_land_cover_vocabulary",
            "test_distribution_orders_rows_by_the_land_cover_vocabulary",
        ),
    },
    "unknown_class_draws_grey": {
        "note": "sdg1531/stats/plots.py:4",
        "reason": (
            "a class outside r.lc_color_by_class is drawn in #9ea7ad, the 'no data' "
            "grey of parameter/ui.py:55-60, where sankey.py:136 and :150 raised "
            "KeyError on colorDict[label]. The companion ValueError('specify a "
            "colour palette') (:73-74) is gone with the argument it guarded."
        ),
        "tests": (
            "test_sankey_falls_back_to_grey_for_a_class_with_no_colour",
            "test_distribution_keeps_a_land_cover_row_outside_the_vocabulary",
        ),
    },
    "distribution_reindexes_missing_classes": {
        "note": "sdg1531/stats/plots.py:5",
        "reason": (
            "distribution_option reindexes onto the three degradation classes where "
            "bar_plot.py:8 hard-selects them, so an AOI for which Earth Engine "
            "reported no 'Improved' group draws a zero-length bar instead of raising "
            "KeyError on ['Improved'] not being in the index."
        ),
        "tests": ("test_distribution_fills_a_missing_improved_group_instead_of_raising",),
    },
    "all_zero_row_is_zero_not_nan": {
        "note": "sdg1531/stats/plots.py:6",
        "reason": (
            "a land cover row whose three classes sum to zero yields 0.0, where "
            "bar_plot.py:10's df.div(df.sum(axis=1)) yielded NaN and matplotlib drew "
            "a gap in the stack."
        ),
        "tests": ("test_distribution_survives_an_all_zero_row",),
    },
    "chart_colours_key_on_untranslated_names": {
        "note": "sdg1531/stats/plots.py:7",
        "reason": (
            "barh_plot(df, color, title) was called with cp.legend "
            "(parameter/ui.py:49-53), whose keys are the TRANSLATED cm.legend.* "
            "strings, while the frame's columns are the untranslated names "
            "bar_plot.py:8 selects on. They lined up only in English; elsewhere "
            "matplotlib silently fell back to its default cycle. _DEGRADATION_COLORS "
            "keys on the untranslated names, so the same three hex values land in "
            "every locale."
        ),
        "tests": ("test_distribution_keeps_the_legacy_legend_colours",),
    },
    "chart_title_dropped_axis_labels_kept": {
        "note": "sdg1531/stats/plots.py:8",
        "reason": (
            "barh_plot's `title` argument (:20) is dropped -- display strings are "
            "the app layer's (spec 4). The two axis names are NOT dropped: "
            "bar_plot.py:17 and :19 hardcode them in English rather than routing "
            "them through the message catalogue, so they are transcriptions."
        ),
        "tests": ("test_distribution_keeps_the_legacy_axis_labels",),
    },
    # --- outside the module notes ---------------------------------------------
    # resolve.py carries NO EXPECTED_DIVERGENCES note of its own, so this entry
    # has no `note` key and MODULE_NOTE_CLAIMS cannot reference it. Reported to
    # the controller as a missing module note rather than fixed here.
    "resolve_requires_a_year": {
        "reason": (
            "resolve._require_year raises SpecError for a missing period endpoint "
            "where the legacy raised TypeError deep inside max() "
            "(indicator_model.py:156-168). Every corpus row sets both endpoints of "
            "the overall period, so resolve() never reaches it."
        ),
        "tests": ("test_a_missing_period_endpoint_is_named_rather_than_escaping_as_a_type_error",),
    },
    # matrix validation moved from the tile layer, which has no module note at all
    # (component/tile/ is not ported). Same shape: no `note` key.
    "matrix_validation_relaxed": {
        "reason": (
            "input_tile.py:310 compared {1,0,-1} to set(flatten) by equality, "
            "rejecting a legitimate two-valued matrix; validate() now uses a subset "
            "test, which only widens what is accepted."
        ),
        "tests": ("test_two_valued_matrix_is_accepted",),
    },
}

# note id -> the register entry that accounts for it. "graph:<scenario>/<layer>"
# names an EXPECTED_DIVERGENCES key, "normalised:<key>" an EXPECTED_NORMALISATIONS
# key, "off_graph:<key>" an EXPECTED_OFF_GRAPH key, and "legacy_only_fails" the
# scenario set. Built from the tables above so a note cannot claim an entry that is
# not there, and checked against the notes `note_modules` FINDS so an entry cannot
# claim a note that is not there.
MODULE_NOTE_CLAIMS: dict[str, str] = {
    **{note: f"graph:{key[0]}/{key[1]}" for key, note in GRAPH_DIVERGENCE_NOTES.items()},
    LEGACY_ONLY_FAILS_NOTE: "legacy_only_fails",
    **{entry["note"]: f"normalised:{name}" for name, entry in EXPECTED_NORMALISATIONS.items()},
    **{
        entry["note"]: f"off_graph:{name}"
        for name, entry in EXPECTED_OFF_GRAPH.items()
        if "note" in entry
    },
}

_NOTE_ANCHOR = re.compile(r"^EXPECTED_DIVERGENCES note\b.*(--|harness)", re.MULTILINE)
_NOTE_ITEM = re.compile(r"^(\d+)\. (.+)$", re.MULTILINE)


def note_modules(repo_root: Path) -> tuple[str, ...]:
    """Every module under ``sdg1531/`` that opens an EXPECTED_DIVERGENCES note.

    DERIVED, not listed. This was a hand-written tuple of seven files, and three
    more modules -- ``export.py``, ``stats/api.py``, ``stats/plots.py`` -- carried
    notes in exactly the format parsed below, each ending "Task 17's parity harness
    must carry all N". Sixteen declared divergences never reached the register, and
    ``test_every_module_divergence_note_is_claimed_by_the_register`` stayed green
    throughout, because the set it checked against was the set it was derived from.
    That is the third hand-maintained roster on this plan to go stale. A scan
    cannot.
    """
    found = []
    for path in sorted((repo_root / "sdg1531").rglob("*.py")):
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        if _NOTE_ANCHOR.search(docstring):
            found.append(path.relative_to(repo_root).as_posix())
    return tuple(found)


def module_notes(repo_root: Path) -> dict[str, str]:
    """Every numbered EXPECTED_DIVERGENCES item under ``sdg1531/``.

    Returns ``{"sdg1531/engine/soc.py:2": "<the item's first line>"}``. The
    anchor is the LAST line that opens a note section, because a module may also
    cross-reference another module's note earlier in its docstring
    (``stats/requests.py`` does, at the start of a wrapped line).
    """
    found: dict[str, str] = {}
    for rel in note_modules(repo_root):
        path = repo_root / rel
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        section = docstring[list(_NOTE_ANCHOR.finditer(docstring))[-1].start() :]
        items = _NOTE_ITEM.findall(section)
        if not items:
            raise AssertionError(f"{rel}'s EXPECTED_DIVERGENCES note has no numbered items")
        for number, first_line in items:
            found[f"{rel}:{number}"] = first_line.strip()
    return found


def matching_entry(scenario: str, layer: str) -> tuple[tuple[str, str], str] | None:
    """The first entry whose patterns match, or None."""
    for (scenario_pattern, layer_pattern), reason in EXPECTED_DIVERGENCES.items():
        if fnmatch(scenario, scenario_pattern) and fnmatch(layer, layer_pattern):
            return (scenario_pattern, layer_pattern), reason
    return None
