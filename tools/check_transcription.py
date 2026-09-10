"""Cross-check sdg1531's constants against component/parameter/*.py.

This is not a pytest test on purpose: it imports the legacy modules, which the
Tier-0 isolation guard forbids the suite from doing. Run it from the repo root:

    python tools/check_transcription.py

Exits 0 and prints one ``OK`` line per constant checked, or raises on the first
mismatch — value OR type. ``==`` alone would let ``1 == 1.0`` or ``True == 1``
through unnoticed; tables.py:155-158 needs the encoded floats bit-identical, so
type drift is exactly the edit class this has to catch (see ``_same``).

What this does NOT cover: everything sourced from component/parameter/ui.py
(``CLIMATE_COEFFICIENTS``, ``JRC_SEASONALITY_TICKS``, ``DISABLED_TRAJECTORIES``,
``tables.DEFAULT_LC_COLORS``, and every value in ``sdg1531.enums``) and from
component/model/indicator_model.py (``IndicatorLayer``'s order). ui.py imports
ipyvuetify and component.message, so ``_load()`` cannot execute it standalone;
those transcriptions were checked by hand during review, not by this script.
``TABLES_UNREACHABLE``/``CATALOG_UNREACHABLE`` below name that gap, module by
module, so it stays visible instead of silently passing as "checked" — and the
closing summary line is built from what actually ran, not asserted outright, so
a skipped check (numpy absent) is named as skipped rather than folded into
"all match".
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdg1531 import catalog, tables  # noqa: E402 — module objects, for __all__ below
from sdg1531.catalog import (  # noqa: E402
    ASSETS,
    INT16_MIN,
    L4_START,
    LAND_COVER_FIRST_YEAR,
    LAND_COVER_MAX_YEAR,
    SENSORS,
    z_coefficient,
)
from sdg1531.tables import (  # noqa: E402
    C_CONVERSION_FACTOR,
    CLIMATE_CONVERSION_MATRIX,
    DEFAULT_LC_CLASS_NAMES,
    DEFAULT_LC_CODES,
    DEFAULT_TRANSITION_MATRIX,
    DEGRADATION_LABELS,
    ESA_LC_CLASSES,
    INPUT_FACTOR,
    IPCC_TRANSITION_CODES,
    MANAGEMENT_FACTOR,
    PROD_PERFORMANCE_LABELS,
    PROD_STATE_5_LABELS,
    PROD_TREND_5_LABELS,
    RECLASSIFICATION_MATRIX,
    TRANSLATION_MATRIX,
)

# Every name in tables.__all__ must land in exactly one of these two sets:
# TABLES_VERIFIED is cross-checked against the legacy source in main() below;
# TABLES_UNREACHABLE names what this script cannot reach, and why, instead of
# letting it slip through unmentioned. A name in neither is a bug in this
# script — main() asserts that before it checks anything.
TABLES_VERIFIED = frozenset(
    {
        "CLIMATE_CONVERSION_MATRIX",
        "C_CONVERSION_FACTOR",
        "DEFAULT_LC_CLASS_NAMES",
        "DEFAULT_LC_CODES",
        "DEFAULT_TRANSITION_MATRIX",
        "DEGRADATION_LABELS",
        "ESA_LC_CLASSES",
        "INPUT_FACTOR",
        "IPCC_TRANSITION_CODES",
        "MANAGEMENT_FACTOR",
        "PROD_PERFORMANCE_LABELS",
        "PROD_STATE_5_LABELS",
        "PROD_TREND_5_LABELS",
        "RECLASSIFICATION_MATRIX",
        "TRANSLATION_MATRIX",
    }
)
# DEFAULT_LC_COLORS is keyed on component/parameter/ui.py's cm.classes.* strings
# (ui.py:61-69). ui.py imports ipyvuetify and component.message, so _load()
# cannot execute it standalone; checked by hand during review, not here.
TABLES_UNREACHABLE = frozenset({"DEFAULT_LC_COLORS", "DEGRADATION_COLORS"})

# Same mechanism as the tables pair above, for catalog.__all__.
CATALOG_VERIFIED = frozenset(
    {
        "ASSETS",
        "INT16_MIN",
        "L4_START",
        "LAND_COVER_FIRST_YEAR",
        "LAND_COVER_MAX_YEAR",
        "SENSORS",
        "z_coefficient",
    }
)
CATALOG_UNREACHABLE = frozenset(
    {
        # ui.py:41-47; ui.py imports ipyvuetify and component.message, so _load()
        # cannot execute it standalone. Checked by hand during review.
        "CLIMATE_COEFFICIENTS",
        # ui.py:39, same reason.
        "JRC_SEASONALITY_TICKS",
        # ui.py:35's "disabled": True flag, same reason.
        "DISABLED_TRAJECTORIES",
        # a type, not a value — nothing to diff against the legacy plain lists;
        # its instances are exercised by the SENSORS/sensor_keys checks above.
        "SensorInfo",
    }
)


def _load(name: str, relative: str) -> ModuleType:
    """Execute a legacy module straight from its path, bypassing ``component``."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_computation() -> ModuleType | None:
    """``computation.py`` needs numpy; skip loudly rather than fail if it's absent."""
    try:
        import numpy  # noqa: F401
    except ImportError:
        return None
    return _load("legacy_computation", "component/parameter/computation.py")


def _same(port: object, legacy: object) -> bool:
    """Structural equality that also catches type drift a bare ``==`` would miss.

    Floats compare by ``float.hex()`` rather than ``==`` (parity must be
    bit-identical, not just numerically equal); containers recurse element-wise
    with an exact ``type(...) is type(...)`` check first, so ``1`` vs ``1.0`` or
    ``True`` vs ``1`` fail instead of quietly passing.
    """
    if type(port) is not type(legacy):
        return False
    if isinstance(port, float) and isinstance(legacy, float):
        return float.hex(port) == float.hex(legacy)
    if isinstance(port, list | tuple) and isinstance(legacy, list | tuple):
        return len(port) == len(legacy) and all(
            _same(p, u) for p, u in zip(port, legacy, strict=True)
        )
    if isinstance(port, dict) and isinstance(legacy, dict):
        return set(port) == set(legacy) and all(_same(port[k], legacy[k]) for k in port)
    return bool(port == legacy)


def _check(name: str, port: object, legacy: object) -> None:
    if not _same(port, legacy):
        raise AssertionError(f"{name}\n  port  : {port!r}\n  legacy: {legacy!r}")
    print("OK  ", name)


def _assert_categorized(module_name: str, exported: list[str], *categories: frozenset[str]) -> None:
    """Every name in ``exported`` must land in exactly one of ``categories``.

    A name in neither is named explicitly in the failure — not just flagged as
    "something is wrong" — so whoever added it sees what they need to classify.
    """
    uncategorized = set(exported) - set().union(*categories)
    assert not uncategorized, (
        f"{module_name}.__all__ has a name this script neither checks nor excuses: "
        f"{sorted(uncategorized)!r}. Add a _check() call for it, or add it to the "
        f"module's *_UNREACHABLE set with a reason."
    )


def main() -> int:
    _assert_categorized("tables", tables.__all__, TABLES_VERIFIED, TABLES_UNREACHABLE)
    _assert_categorized("catalog", catalog.__all__, CATALOG_VERIFIED, CATALOG_UNREACHABLE)

    matrix = _load("legacy_matrix", "component/parameter/matrix.py")
    sensor = _load("legacy_sensor", "component/parameter/sensor.py")

    default = [list(r) for r in DEFAULT_TRANSITION_MATRIX]
    _check("trans_matrix", default, matrix.default_trans_matrix)
    _check("ipcc", list(IPCC_TRANSITION_CODES), matrix.IPCC_lc_change_matrix)
    _check("translation", [list(r) for r in TRANSLATION_MATRIX], matrix.translation_matrix)
    _check("esa", list(ESA_LC_CLASSES), matrix.ESA_lc_classes)
    _check("reclass", list(RECLASSIFICATION_MATRIX), matrix.reclassification_matrix)
    climate = [list(r) for r in CLIMATE_CONVERSION_MATRIX]
    _check("climate_conv", climate, matrix.climate_conversion_matrix)
    _check("c_conv", list(C_CONVERSION_FACTOR), matrix.c_conversion_factor)
    _check("management", list(MANAGEMENT_FACTOR), matrix.management_factor)
    _check("input", list(INPUT_FACTOR), matrix.input_factor)
    _check("lc_code", list(DEFAULT_LC_CODES), matrix.lc_code)
    _check("lc_class", list(DEFAULT_LC_CLASS_NAMES), matrix.lc_class)
    _check("degradation", dict(DEGRADATION_LABELS), matrix.degradation_class)
    _check("trend5", dict(PROD_TREND_5_LABELS), matrix.prod_trend_5_class)
    _check("state5", dict(PROD_STATE_5_LABELS), matrix.prod_state_5_class)
    _check("performance", dict(PROD_PERFORMANCE_LABELS), matrix.prod_performance_class)

    legacy_assets = {
        "precipitation": sensor.precipitation,
        "land_cover_ic": sensor.land_cover_ic,
        "jrc_water": sensor.jrc_water,
        "soil_taxonomy": sensor.soil_taxonomy,
        "soc": sensor.soc,
        "ipcc_climate_zones": sensor.ipcc_climate_zones,
        "wte": sensor.wte,
        "gaes": sensor.gaes,
        "aez": sensor.aez,
        "hru": sensor.hru,
    }
    _check("assets", dict(ASSETS), legacy_assets)
    _check("l4_start", L4_START, sensor.L4_start)
    _check("land_cover_first_year", LAND_COVER_FIRST_YEAR, sensor.land_cover_first_year)
    _check("land_cover_max_year", LAND_COVER_MAX_YEAR, sensor.land_cover_max_year)

    # key order is load-bearing (catalog.py:45-46): a dropped or reordered sensor
    # must fail here, not just a changed value for a sensor that's still present
    _check("sensor_keys", list(SENSORS), list(sensor.sensors))
    for name, info in SENSORS.items():
        collection = info.collection_id
        port = [
            list(collection) if isinstance(collection, tuple) else collection,
            info.scale,
            info.code,
            info.level,
        ]
        _check(f"sensor:{name}", port, sensor.sensors[name])

    # matched/skipped drive the closing summary below, so it can only ever
    # describe checks that actually ran — not a hardcoded claim of full coverage
    matched = [
        f"{len(TABLES_VERIFIED)} tables",
        f"{len(SENSORS)} sensors (keys and values)",
        "assets",
        "year bounds",
    ]
    skipped: list[str] = []

    computation = _load_computation()
    if computation is None:
        print("SKIP  int16_min, z_coefficient — numpy is not installed")
        skipped.append("int16_min, z_coefficient (numpy not installed)")
    else:
        _check("int16_min", INT16_MIN, computation.int_16_min)
        for n in (4, 5, 10, 23, 40):
            _check(f"z_coefficient({n})", z_coefficient(n), computation.z_coefficient(n))
        matched.append("int16_min + z_coefficient")

    summary = f"checked {' + '.join(matched)} against the legacy source — all match."
    if skipped:
        summary += f" SKIPPED: {'; '.join(skipped)}."
    summary += (
        " NOT checked here (ui.py cannot be imported standalone): "
        "tables.DEFAULT_LC_COLORS, catalog.CLIMATE_COEFFICIENTS, "
        "catalog.JRC_SEASONALITY_TICKS, catalog.DISABLED_TRAJECTORIES, and every "
        "sdg1531.enums value."
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
