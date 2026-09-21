"""Cross-check sdg1531.scheme against indicator_model.py's property bodies.

Not a pytest test on purpose: it needs matplotlib, which the domain deliberately
does not depend on, and it re-executes the legacy property bodies verbatim
against the raw CSV rows. Run it from the repo root:

    python tools/check_scheme.py

Exits 0 and prints one ``OK`` line per property, or raises on the first mismatch.

**A one-shot artefact, retained until ``component/`` is deleted.** Nothing runs it:
it is not collected by pytest, no CI job invokes it, and unlike its sibling
``tools/check_transcription.py`` -- which ``tests/test_constants.py``'s docstring
names -- nothing in the suite even mentioned it, so a reader had no way to discover
it existed. It records no run date either, so "it passed" is a claim about whenever
someone last typed the command. What it checks is pinned in the suite by
``tests/test_scheme.py`` and ``tests/test_palette.py``, against literals rather
than against the legacy; this is the against-the-legacy half, and it goes when the
tree it reads goes.
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

from sdg1531.scheme import LandCoverScheme, parse_custom_matrix_csv, read_matrix_csv  # noqa: E402
from sdg1531.tables import DEFAULT_LC_COLORS  # noqa: E402

GOLDEN = REPO_ROOT / "tests" / "data" / "ipccsx_matrix.csv"

# Same fixture as tests/test_scheme.py's OUT_OF_ORDER: codes 30/10/20 are *not*
# ascending in CSV order, unlike the golden's 10..22. Needed because the golden
# alone can't tell "sorted by code" apart from "left as CSV order" — its codes
# already happen to be ascending, so a `sorted()` that silently became a no-op
# would still pass every golden check.
OUT_OF_ORDER = (
    "Land cover,2015,Cane,Apple,Bean\r\n"
    "2000,Code,30,10,20\r\n"
    "Cane,30,0,1,-1\r\n"
    "Apple,10,-1,0,1\r\n"
    "Bean,20,1,-1,0"
)


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
    # run_15_3_1.py:217-219 and :266
    combination_labels = [f"{a}_{b}" for a in classlist_start for b in classlist_end]
    code_to_name_start = dict(zip(codelist_start, classlist_start, strict=True))

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
    _check("combination_labels", list(scheme.combination_labels), combination_labels)
    _check("code_to_name_start", scheme.code_to_name_start(), code_to_name_start)
    _check("palette", list(scheme.palette()), colors)
    _check("lc_color", scheme.color_by_class(), lc_color)

    # the golden's codes (10..22) are already ascending, so `sorted()` in
    # code_ordered_names/color_by_class is a no-op there — dropping it entirely
    # would still pass every check above. This fixture's codes (30, 10, 20) are
    # not ascending, so it actually exercises the sort.
    ooo_rows = list(csv.reader(OUT_OF_ORDER.splitlines()))
    ooo_classlist_start = [re.sub(pattern, "", r[0].strip()) for r in ooo_rows[2:]]
    ooo_codelist_start = [int(r[1]) for r in ooo_rows[2:]]
    ooo_by_code = dict(zip(ooo_codelist_start, ooo_classlist_start, strict=True))
    ooo_sorted_classes = list(dict(sorted(ooo_by_code.items())).values())
    random.seed(100)
    ooo_colors = random.sample(all_colors, len(ooo_classlist_start))
    ooo_lc_color = dict(zip(ooo_sorted_classes, ooo_colors, strict=True))

    ooo_scheme = parse_custom_matrix_csv(read_matrix_csv(OUT_OF_ORDER))
    _check("ooo_code_ordered_names", list(ooo_scheme.code_ordered_names), ooo_sorted_classes)
    _check("ooo_color_by_class", ooo_scheme.color_by_class(), ooo_lc_color)

    # the non-custom branch: indicator_model.py's else-path is a plain lookup,
    # not the sampler above, and nothing exercised it until now.
    default_scheme = LandCoverScheme.default()
    _check("default_palette", list(default_scheme.palette()), list(DEFAULT_LC_COLORS.values()))
    _check("default_color_by_class", default_scheme.color_by_class(), dict(DEFAULT_LC_COLORS))

    print("scheme matches the legacy properties")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
