"""Cross-check sdg1531's constants against component/parameter/*.py.

This is not a pytest test on purpose: it imports the legacy modules, which the
Tier-0 isolation guard forbids the suite from doing. Run it from the repo root:

    python tools/check_transcription.py

Exits 0 and prints one ``OK`` line per constant, or raises on the first mismatch.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdg1531.catalog import SENSORS  # noqa: E402
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


def _load(name: str, relative: str) -> ModuleType:
    """Execute a legacy module straight from its path, bypassing ``component``."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check(name: str, port: object, legacy: object) -> None:
    if port != legacy:
        raise AssertionError(f"{name}\n  port  : {port!r}\n  legacy: {legacy!r}")
    print("OK  ", name)


def main() -> int:
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

    for name, info in SENSORS.items():
        collection = info.collection_id
        port = [
            list(collection) if isinstance(collection, tuple) else collection,
            info.scale,
            info.code,
            info.level,
        ]
        _check(f"sensor:{name}", port, sensor.sensors[name])

    print("all transcriptions match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
