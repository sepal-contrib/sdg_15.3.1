"""The app package exists, imports clean, and its catalogue is valid."""

from __future__ import annotations

import app
from app.message import messages


def test_app_exports_nothing():
    """`app` is a namespace, not a re-export layer: importing it must not
    pull in solara, pysepal or ee as a side effect of touching the package."""
    assert app.__all__ == ()


# Task 14 owns translations, so fr's overlay is a deliberate partial one until
# then. Pinned exactly rather than excluded wholesale: a task after this one
# that adds another English key with no fr translation must fail here, not
# silently grow the debt with nothing recording that it happened.
_UNTRANSLATED_FR_KEYS = frozenset(
    {
        "panel.title",
        "panel.description",
        "step.aoi",
        "step.productivity",
        "step.land_cover",
        "step.soc",
        "step.run",
        "aoi.description",
        "aoi.selected",
        "productivity.description",
        "productivity.sensors",
        "productivity.index",
        "productivity.trajectory",
        "productivity.lceu",
        "productivity.lookup",
        "productivity.threshold",
        "productivity.index_value.ndvi",
        "productivity.index_value.evi",
        "productivity.index_value.msvi",
        "productivity.trajectory_value.ndvi_trend",
        "productivity.trajectory_value.p_res_trend",
        "productivity.trajectory_value.s_res_trend",
        "productivity.trajectory_value.ue_trend",
        "productivity.lceu_value.gaes",
        "productivity.lceu_value.aez",
        "productivity.lceu_value.wte",
        "productivity.lceu_value.hru",
        "productivity.lceu_value.calculate",
        "land_cover.description",
        "land_cover.source",
        "land_cover.water_mask",
        "land_cover.water_mask_other_arm",
        "land_cover.esa",
        "land_cover.custom",
        "land_cover.start_asset",
        "land_cover.end_asset",
        "soc.description",
        "soc.start",
        "soc.end",
        "run.description",
        "run.start_year",
        "run.end_year",
        "run.build",
        "run.built",
        "run.blocked",
        "layers.title",
        "layers.description",
        "layers.show",
        "layers.shown",
        "layers.build_first",
        "results.title",
        "results.description",
        "results.compute",
        "results.computed",
        "results.build_first",
        "zonal.title",
        "zonal.description",
        "zonal.compute",
        "zonal.download",
        "zonal.ready",
        "zonal.build_first",
    }
)


def test_the_catalogue_is_valid():
    """catalog() validates English at import; check() covers every other locale.

    ``missing_key`` is allowed only for exactly ``_UNTRANSLATED_FR_KEYS``. Any
    other code -- placeholder mismatch, bad plural, shape mismatch -- or any
    missing key beyond that pinned set, is a real translation defect and must
    still be empty.
    """
    problems = messages.check()
    missing = {p.key for p in problems if p.code == "missing_key"}
    other = tuple(p for p in problems if p.code != "missing_key")

    assert missing == _UNTRANSLATED_FR_KEYS
    assert other == ()
