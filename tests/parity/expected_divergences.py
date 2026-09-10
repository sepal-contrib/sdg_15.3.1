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

The registers, because a difference can show up in five ways:

``EXPECTED_DIVERGENCES``
    a GRAPH PAIR that differs and is licensed. Keys are (scenario pattern, layer
    pattern), both fnmatch globs. The table fails in BOTH directions: an unlisted
    divergence fails, a listed divergence that no longer appears fails, and an
    entry that matches no scenario/layer pair at all fails. That is what keeps it
    from rotting into a list of excuses -- but it is not what keeps an entry
    narrow, and nothing can be except reading it.
``EXPECTED_NORMALISATIONS``
    a graph pair that differs by a known node, which the harness SPLICES OUT and
    then requires byte equality on the remainder. This is strictly stronger than a
    licence and is where a difference belongs whenever it can be described
    structurally: the normalisation is written down as code, tested for what it
    refuses as well as what it removes, and it leaves the rest of the layer
    compared.
``EXPECTED_LEGACY_AND_PORT_BOTH_FAIL``
    scenarios BOTH trees refuse. There is no graph pair, so these are not
    divergences and must not be listed above.
``EXPECTED_COMPATIBILITY_DIVERGENCES``
    the layers a non-default :class:`~sdg1531.spec.Compatibility` moves. These are
    not divergences either, and the harness does NOT license them: see below.
``EXPECTED_OFF_GRAPH``
    divergences that are real but produce no graph pair in this corpus, so the
    both-directions rule cannot police them. Each names the test that does.

Every entry cites the numbered ``EXPECTED_DIVERGENCES`` note in the port module
that declares it, and ``MODULE_NOTE_CLAIMS`` below maps every such note to the
register entry that accounts for it. ``tests/parity/test_parity.py`` checks that
mapping in both directions against the notes actually found in the source, so a
new module note cannot appear without a register entry and a register entry
cannot cite a note that no longer exists.
"""

from __future__ import annotations

import ast
import re
from fnmatch import fnmatch
from pathlib import Path

__all__ = [
    "EXPECTED_COMPATIBILITY_DIVERGENCES",
    "EXPECTED_DIVERGENCES",
    "EXPECTED_LEGACY_AND_PORT_BOTH_FAIL",
    "EXPECTED_NORMALISATIONS",
    "EXPECTED_OFF_GRAPH",
    "GRAPH_DIVERGENCE_NOTES",
    "MODULE_NOTE_CLAIMS",
    "NOTE_MODULES",
    "matching_entry",
    "module_notes",
]

EXPECTED_DIVERGENCES: dict[tuple[str, str], str] = {
    # engine/land_cover.py note 4: "water_mask_pixel > 9 with a None default".
    # land_cover.py:58 reads
    #     if model.start_lc and model.end_lc and model.water_mask_pixel > 9:
    # so with a CUSTOM land cover source and a JRC or asset-band mask,
    # water_mask_pixel is None and the legacy raises TypeError before it builds
    # anything at all. The three-arm union removes the comparison, so these
    # scenarios go from "the legacy crashes" to "the port succeeds" - a
    # whole-scenario divergence, hence the "*" layer pattern.
    #
    # The set is exactly the _TABLE rows with land_cover in {custom_full,
    # custom_half} AND water in {jrc, asset_band}. Rows with a custom source and a
    # PIXEL mask (s06, s07, s10, s11, s19, s21, s25, s27) are deliberately absent:
    # 70 > 9 and 10 > 9 are both true, the legacy takes branch 1, and the port
    # emits the same graph.
    ("s05", "*"): "water mask union replaces the None-comparison branch (land_cover.py:58)",
    ("s08", "*"): "water mask union replaces the None-comparison branch (land_cover.py:58)",
    ("s09", "*"): "water mask union replaces the None-comparison branch (land_cover.py:58)",
    ("s12", "*"): "water mask union replaces the None-comparison branch (land_cover.py:58)",
    ("s17", "*"): "water mask union replaces the None-comparison branch (land_cover.py:58)",
    ("s18", "*"): "water mask union replaces the None-comparison branch (land_cover.py:58)",
    ("s20", "*"): "water mask union replaces the None-comparison branch (land_cover.py:58)",
    ("s26", "*"): "water mask union replaces the None-comparison branch (land_cover.py:58)",
    ("s28", "*"): "water mask union replaces the None-comparison branch (land_cover.py:58)",
}

# Which module note licenses each graph entry above. Separate from the reason
# strings because `matching_entry` returns those verbatim to a failing assertion.
GRAPH_DIVERGENCE_NOTES: dict[tuple[str, str], str] = {
    ("s05", "*"): "sdg1531/engine/land_cover.py:4",
    ("s08", "*"): "sdg1531/engine/land_cover.py:4",
    ("s09", "*"): "sdg1531/engine/land_cover.py:4",
    ("s12", "*"): "sdg1531/engine/land_cover.py:4",
    ("s17", "*"): "sdg1531/engine/land_cover.py:4",
    ("s18", "*"): "sdg1531/engine/land_cover.py:4",
    ("s20", "*"): "sdg1531/engine/land_cover.py:4",
    ("s26", "*"): "sdg1531/engine/land_cover.py:4",
    ("s28", "*"): "sdg1531/engine/land_cover.py:4",
}

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
EXPECTED_NORMALISATIONS: dict[str, dict[str, str]] = {
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
        "test": "test_the_splice_turns_the_port_graph_into_the_legacy_one",
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

# Divergences that are real but produce no graph pair to compare, so the
# both-directions rule cannot police them. Each names the test that does.
EXPECTED_OFF_GRAPH: dict[str, dict[str, str]] = {
    # --- engine/integration.py ------------------------------------------------
    "vi_threshold_narrowing": {
        "note": "sdg1531/engine/integration.py:1",
        "reason": (
            "require_float raises SpecError for an unset spec.threshold where "
            "vi_threshold (integration.py:410-415) built an Image.gt node with its "
            "image2 argument absent. Every corpus row sets a threshold, so the "
            "harness never reaches it."
        ),
        "test": "test_an_unset_threshold_raises_on_every_rung_that_consumes_it",
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
        "test": "test_a_pixel_value_mask_over_esa_cci_rejects_a_non_water_code",
    },
    "unset_water_mask": {
        "note": "sdg1531/engine/land_cover.py:2",
        "reason": (
            "an unset spec.water_mask raises SpecError where land_cover.py:74-81 "
            "built a JRC mask from model.seasonality. RunSpec allows None; the "
            "corpus never uses it, because a scenario with no mask has no graph."
        ),
        "test": "test_an_unset_water_mask_is_rejected",
    },
    "unrecognised_arm": {
        "note": "sdg1531/engine/land_cover.py:3",
        "reason": (
            "an unrecognised land cover or water mask arm raises SpecError. Both "
            "are closed unions, so no RunSpec the corpus can build reaches it."
        ),
        "test": "test_an_unset_water_mask_is_rejected",
    },
    # --- engine/productivity.py -----------------------------------------------
    "unresolved_period_bound": {
        "note": "sdg1531/engine/productivity.py:1",
        "reason": (
            "require_int raises SpecError for an unset trend/state/performance "
            "bound where productivity.py:120-122 and :196-199 handed None to "
            "ee.Filter and to arithmetic. Every corpus row resolves all three."
        ),
        "test": "test_build_trajectory_requires_a_resolved_trend",
    },
    "unknown_lceu": {
        "note": "sdg1531/engine/productivity.py:2",
        "reason": (
            "an unknown Lceu raises SpecError where productivity.py:92-116 fell "
            "through to UnboundLocalError. Lceu is closed; the corpus covers all "
            "five members."
        ),
        "test": "test_unknown_lceu_raises_a_spec_error",
    },
    "unknown_trajectory": {
        "note": "sdg1531/engine/productivity.py:3",
        "reason": (
            "an unknown Trajectory raises SpecError where productivity.py:30-51 "
            "left z_score unbound. Trajectory is closed."
        ),
        "test": "test_unknown_trajectory_raises_a_spec_error",
    },
    "s_res_trend_unavailable": {
        "note": "sdg1531/engine/productivity.py:4",
        "reason": (
            "S_RES_TREND raises SpecError where productivity.py:41-43 raised a bare "
            "NameError. It is excluded from the corpus for exactly that reason: it "
            "has no legacy graph to compare against."
        ),
        "test": "test_s_res_trend_raises_a_spec_error_not_a_name_error",
    },
    # --- engine/soc.py --------------------------------------------------------
    "unrecognised_climate_arm": {
        "note": "sdg1531/engine/soc.py:1",
        "reason": (
            "an unrecognised spec.climate arm raises SpecError; the legacy if/else "
            "at soil_organic_carbon.py:19-27 is total, so there is no arm to "
            "compare and no RunSpec that reaches this."
        ),
        "test": "test_an_unsupported_climate_regime_raises_spec_error",
    },
    "zero_climate_coefficient": {
        "note": "sdg1531/engine/soc.py:2",
        "reason": (
            "FixedClimate(coefficient=0.0) takes the fixed branch and builds "
            "ee.Image(1).divide(0.0), where soil_organic_carbon.py:19's truthiness "
            "test sent it to the per-pixel IPCC remap -- a different graph. None of "
            "the five UI coefficients is 0.0, so the corpus cannot reach it."
        ),
        "test": "test_a_zero_coefficient_takes_the_fixed_branch_where_the_legacy_took_per_pixel",
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
        "test": "test_start_not_before_end_is_fatal",
    },
    "layers_is_total": {
        "note": "sdg1531/engine/indicator.py:3",
        "reason": (
            "IndicatorMaps.layers() is a total mapping over the seven "
            "IndicatorLayer members where indicator_n_category_label "
            "(run_15_3_1.py:427-448) had no else and raised UnboundLocalError. "
            "That is a Python-level shape, not a graph node."
        ),
        "test": "test_layers_returns_exactly_seven_entries_in_spec_order",
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
        "test": "test_the_statistics_vocabulary_deliberately_differs_from_the_export_vocabulary",
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
        "test": "test_the_two_area_reducers_keep_the_legacy_constant_types",
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
        "test": "test_empty_payload_raises_statistics_error",
    },
    "distinct_pixel_values_sorted": {
        "note": "sdg1531/stats/decode.py:2",
        "reason": (
            "decode_distinct_pixel_values sorts; custom_lc_values "
            "(run_15_3_1.py:421-422) returned histogram key order. Same integers, "
            "same count, different order."
        ),
        "test": "test_decode_distinct_pixel_values_returns_sorted_ints",
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
        "test": "test_decode_transition_areas_rejects_a_malformed_scheme",
    },
    "areas_by_land_cover_column_name": {
        "note": "sdg1531/stats/decode.py:4",
        "reason": (
            "the class column is layer.value (the snake id) where "
            "run_15_3_1.py:297 used the translated indicator_name. No value, row or "
            "ordering differs -- display strings are the app layer's."
        ),
        "test": "test_decode_areas_by_land_cover_uses_the_five_class_labels_for_productivity_state",
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
        "test": "test_a_missing_period_endpoint_is_named_rather_than_escaping_as_a_type_error",
    },
    # matrix validation moved from the tile layer, which has no module note at all
    # (component/tile/ is not ported). Same shape: no `note` key.
    "matrix_validation_relaxed": {
        "reason": (
            "input_tile.py:310 compared {1,0,-1} to set(flatten) by equality, "
            "rejecting a legitimate two-valued matrix; validate() now uses a subset "
            "test, which only widens what is accepted."
        ),
        "test": "test_two_valued_matrix_is_accepted",
    },
}

# The port modules that carry a numbered EXPECTED_DIVERGENCES note in their
# docstring. `test_parity.py` discovers the notes in these files and checks them
# against MODULE_NOTE_CLAIMS in both directions.
NOTE_MODULES: tuple[str, ...] = (
    "sdg1531/engine/integration.py",
    "sdg1531/engine/land_cover.py",
    "sdg1531/engine/productivity.py",
    "sdg1531/engine/soc.py",
    "sdg1531/engine/indicator.py",
    "sdg1531/stats/requests.py",
    "sdg1531/stats/decode.py",
)

# note id -> the register entry that accounts for it. "graph:<scenario>/<layer>"
# names an EXPECTED_DIVERGENCES key, "normalised:<key>" an EXPECTED_NORMALISATIONS
# key and "off_graph:<key>" an EXPECTED_OFF_GRAPH key. Built from the three tables
# above so a note cannot claim an entry that is not there, and checked against the
# notes found in NOTE_MODULES so an entry cannot claim a note that is not there.
MODULE_NOTE_CLAIMS: dict[str, str] = {
    **{note: f"graph:{key[0]}/{key[1]}" for key, note in GRAPH_DIVERGENCE_NOTES.items()},
    **{entry["note"]: f"normalised:{name}" for name, entry in EXPECTED_NORMALISATIONS.items()},
    **{
        entry["note"]: f"off_graph:{name}"
        for name, entry in EXPECTED_OFF_GRAPH.items()
        if "note" in entry
    },
}

_NOTE_ANCHOR = re.compile(r"^EXPECTED_DIVERGENCES note\b.*(--|harness)", re.MULTILINE)
_NOTE_ITEM = re.compile(r"^(\d+)\. (.+)$", re.MULTILINE)


def module_notes(repo_root: Path) -> dict[str, str]:
    """Every numbered EXPECTED_DIVERGENCES item in :data:`NOTE_MODULES`.

    Returns ``{"sdg1531/engine/soc.py:2": "<the item's first line>"}``. The
    anchor is the LAST line that opens a note section, because a module may also
    cross-reference another module's note earlier in its docstring
    (``stats/requests.py`` does, at the start of a wrapped line).
    """
    found: dict[str, str] = {}
    for rel in NOTE_MODULES:
        path = repo_root / rel
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        anchors = list(_NOTE_ANCHOR.finditer(docstring))
        if not anchors:
            raise AssertionError(f"{rel} carries no EXPECTED_DIVERGENCES note section")
        section = docstring[anchors[-1].start() :]
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
