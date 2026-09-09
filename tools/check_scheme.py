"""Cross-check sdg1531.scheme against indicator_model.py's property bodies.

Not a pytest test on purpose: it needs matplotlib, which the domain deliberately
does not depend on, and it re-executes the legacy property bodies verbatim
against the raw CSV rows. Run it from the repo root:

    python tools/check_scheme.py

Exits 0 and prints one ``OK`` line per property, or raises on the first mismatch.
"""

from __future__ import annotations

import csv
import random
import re
import sys
from pathlib import Path

import matplotlib.colors as pltc

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdg1531.scheme import parse_custom_matrix_csv, read_matrix_csv  # noqa: E402

GOLDEN = REPO_ROOT / "tests" / "data" / "ipccsx_matrix.csv"


def _check(name: str, port: object, legacy: object) -> None:
    if port != legacy:
        raise AssertionError(f"{name}\n  port  : {port!r}\n  legacy: {legacy!r}")
    print("OK  ", name)


def main() -> int:
    with GOLDEN.open("r") as handle:  # indicator_model.py:316-320
        rows = list(csv.reader(handle))

    pattern = re.compile(r"[^a-zA-Z -]+")  # indicator_model.py:186
    classlist_end = [re.sub(pattern, "", x.strip()) for x in rows[0][2:]]
    classlist_start = [re.sub(pattern, "", r[0].strip()) for r in rows[2:]]
    codelist_end = [int(v) for v in rows[1][2:]]
    codelist_start = [int(r[1]) for r in rows[2:]]
    transition = [r[2:] for r in rows[2:]]
    flatten = [int(cell) for row in transition for cell in row]
    combinations = [int(str(a) + str(b)) for a in codelist_start for b in codelist_end]

    all_colors = [hx for _, hx in pltc.cnames.items()]  # indicator_model.py:248-250
    random.seed(100)
    colors = random.sample(all_colors, len(classlist_start))
    by_code = dict(zip(codelist_start, classlist_start, strict=True))
    sorted_classes = list(dict(sorted(by_code.items())).values())
    lc_color = dict(zip(sorted_classes, colors, strict=True))

    scheme = parse_custom_matrix_csv(read_matrix_csv(GOLDEN.read_text(encoding="utf-8")))
    _check("classlist_end", list(scheme.end_names), classlist_end)
    _check("classlist_start", list(scheme.start_names), classlist_start)
    _check("codelist_end", list(scheme.end_codes), codelist_end)
    _check("codelist_start", list(scheme.start_codes), codelist_start)
    _check("flatten", list(scheme.matrix.flatten()), flatten)
    _check("combinations", list(scheme.class_combinations), combinations)
    _check("palette", list(scheme.palette()), colors)
    _check("lc_color", scheme.color_by_class(), lc_color)

    print("scheme matches the legacy properties")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
