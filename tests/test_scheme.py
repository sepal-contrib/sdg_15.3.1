"""scheme.py — the land-cover vocabulary and the transition matrix as values.

Transcribed behaviour lives in indicator_model.py:172-266 and 315-321, plus the
label/combination construction at run_15_3_1.py:217-219 and :266.

Every assertion here is against a literal. The against-the-legacy comparison is
``tools/check_scheme.py``, which re-executes those property bodies verbatim against
the raw CSV rows; it needs matplotlib and imports the legacy tree, so it cannot be
collected here. It is named from this docstring because nothing else named it at
all -- see its own header for what it is and when it goes.
"""

from __future__ import annotations

import dataclasses
import random

import pytest
from conftest import REPO_ROOT

from sdg1531.errors import CustomMatrixError
from sdg1531.palette import CSS4_HEX
from sdg1531.scheme import (
    LandCoverScheme,
    TransitionMatrix,
    parse_custom_matrix_csv,
    read_matrix_csv,
)
from sdg1531.tables import DEFAULT_LC_CLASS_NAMES, DEFAULT_LC_CODES, DEFAULT_TRANSITION_MATRIX

GOLDEN = REPO_ROOT / "tests" / "data" / "ipccsx_matrix.csv"


@pytest.fixture
def golden_rows() -> list[list[str]]:
    return read_matrix_csv(GOLDEN.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# TransitionMatrix
# --------------------------------------------------------------------------
def test_default_matrix_is_the_legacy_table() -> None:
    assert TransitionMatrix.default().rows == DEFAULT_TRANSITION_MATRIX


def test_module_default_cannot_be_mutated_through_an_instance() -> None:
    """widget/transition_matrix.py:46 index-assigns into pm.default_trans_matrix
    in place. Under Solara that leaks one user's matrix into every session in the
    worker (spec §7). Neither route may exist any more."""
    m = TransitionMatrix.default()

    with pytest.raises(dataclasses.FrozenInstanceError):
        m.rows = ((0,),)  # type: ignore[misc]

    with pytest.raises(TypeError):
        m.rows[0][0] = 99  # type: ignore[index]

    with pytest.raises(TypeError):
        m.rows[0] = (9,) * 7  # type: ignore[index]

    assert TransitionMatrix.default().rows == DEFAULT_TRANSITION_MATRIX


def test_default_matrix_is_pristine_after_editing_a_copy() -> None:
    a = TransitionMatrix.default()
    b = a.with_cell(0, 1, 1)

    assert b.rows[0][1] == 1
    assert a.rows[0][1] == -1
    assert a.rows == DEFAULT_TRANSITION_MATRIX
    assert DEFAULT_TRANSITION_MATRIX[0][1] == -1


def test_edited_matrix_is_not_default() -> None:
    """indicator_model.py:305 compares the module-level list with itself (it is
    stored without a copy at :53), so custom_matrix was permanently False."""
    a = TransitionMatrix.default()
    assert a.is_default() is True
    assert a.with_cell(6, 6, 1).is_default() is False
    # value semantics, not identity: an equal matrix built from scratch is default
    assert TransitionMatrix.from_list([list(r) for r in DEFAULT_TRANSITION_MATRIX]).is_default()


def test_flatten_is_row_major() -> None:
    """transcribed from indicator_model.py:230-242 — `for sublist in matrix for
    item in sublist`, i.e. row by row."""
    m = TransitionMatrix.from_list([[1, 2, 3], [4, 5, 6]])
    assert m.flatten() == (1, 2, 3, 4, 5, 6)

    flat = TransitionMatrix.default().flatten()
    assert len(flat) == 49
    assert flat[:7] == (0, -1, -1, -1, -1, -1, 0)
    assert flat[7:14] == (1, 0, 1, -1, -1, -1, 0)
    assert flat[-7:] == (0, 0, 0, 0, 0, 0, 0)


def test_with_cell_rejects_out_of_range() -> None:
    m = TransitionMatrix.default()
    with pytest.raises(IndexError):
        m.with_cell(7, 0, 1)
    with pytest.raises(IndexError):
        m.with_cell(0, 7, 1)


def test_to_list_from_list_round_trip() -> None:
    m = TransitionMatrix.default()
    assert TransitionMatrix.from_list(m.to_list()) == m
    assert m.to_list() == [list(r) for r in DEFAULT_TRANSITION_MATRIX]
    assert isinstance(m.to_list()[0], list)


def test_from_list_coerces_strings_to_int() -> None:
    m = TransitionMatrix.from_list([["0", "-1"], ["1", "0"]])
    assert m.rows == ((0, -1), (1, 0))


def test_constructor_coerces_rows_like_from_list() -> None:
    """Without this, ``TransitionMatrix(rows=[[...]])`` would be a frozen
    instance wrapping mutable lists, and ``is_default()`` would then compare
    ``list != tuple`` and report False for a semantically-default matrix."""
    lists = [list(row) for row in DEFAULT_TRANSITION_MATRIX]
    m = TransitionMatrix(rows=lists)  # type: ignore[arg-type]

    assert m.is_default() is True
    assert m.rows == DEFAULT_TRANSITION_MATRIX
    assert isinstance(m.rows, tuple)
    assert all(isinstance(row, tuple) for row in m.rows)


def test_ragged_rows_are_rejected() -> None:
    """flatten() reads rows in order regardless of length, so a ragged matrix
    silently shifts every value after a short or long row once it is zipped
    against LandCoverScheme.class_combinations in resolve.py — a wrong-but-
    plausible transition table, not a loud error. _matrix_from_json is the one
    path that can hand the constructor a ragged shape read straight off disk,
    bypassing sdg1531.validate entirely, so the guard belongs here too."""
    with pytest.raises(ValueError, match="same length"):
        TransitionMatrix(rows=((0, -1, 1), (-1, 0)))


def test_a_single_row_is_never_ragged() -> None:
    # one row has nothing to disagree with — this is a valid (if unusual) shape
    assert TransitionMatrix(rows=((0, -1, 1, 0),)).rows == ((0, -1, 1, 0),)


# --------------------------------------------------------------------------
# LandCoverScheme — the default vocabulary
# --------------------------------------------------------------------------
def test_default_scheme_uses_the_seven_ipcc_classes() -> None:
    s = LandCoverScheme.default()
    assert s.start_names == DEFAULT_LC_CLASS_NAMES
    assert s.end_names == DEFAULT_LC_CLASS_NAMES
    assert s.start_codes == DEFAULT_LC_CODES
    assert s.end_codes == DEFAULT_LC_CODES
    assert s.is_custom is False
    assert s.matrix.is_default()


def test_default_scheme_accepts_an_edited_matrix() -> None:
    edited = TransitionMatrix.default().with_cell(0, 1, 1)
    s = LandCoverScheme.default(matrix=edited)
    assert s.matrix is edited
    assert s.matrix.is_default() is False
    assert s.start_names == DEFAULT_LC_CLASS_NAMES
    # editing the matrix must not flip the "did the user supply a CSV" flag
    assert s.is_custom is False


def test_is_custom_alone_switches_palette_not_the_vocabulary_shape() -> None:
    """``is_custom`` is the single source of truth for the palette/colour branch —
    nothing may re-derive it from the shape of start_names/start_codes. Build a
    scheme whose vocabulary looks exactly like a custom (non-IPCC) CSV but with
    ``is_custom=False``, and confirm palette()/color_by_class() still take the
    non-custom branch."""
    custom_shaped = LandCoverScheme(
        start_names=("Cane", "Apple", "Bean"),
        start_codes=(30, 10, 20),
        end_names=("Cane", "Apple", "Bean"),
        end_codes=(30, 10, 20),
        matrix=TransitionMatrix.from_list([[0, 1, -1], [-1, 0, 1], [1, -1, 0]]),
        is_custom=False,
    )
    from sdg1531.tables import DEFAULT_LC_COLORS

    assert custom_shaped.palette() == tuple(DEFAULT_LC_COLORS.values())
    assert custom_shaped.color_by_class() == dict(DEFAULT_LC_COLORS)


def test_default_class_combinations_are_the_ipcc_codes() -> None:
    """transcribed from indicator_model.py:221-227."""
    from sdg1531.tables import IPCC_TRANSITION_CODES

    assert LandCoverScheme.default().class_combinations == IPCC_TRANSITION_CODES


def test_default_combination_labels() -> None:
    """transcribed from run_15_3_1.py:217-219."""
    labels = LandCoverScheme.default().combination_labels
    assert len(labels) == 49
    assert labels[0] == "Tree-covered areas_Tree-covered areas"
    assert labels[1] == "Tree-covered areas_Grassland"
    assert labels[-1] == "Water bodies_Water bodies"


def test_default_palette_and_colours() -> None:
    from sdg1531.tables import DEFAULT_LC_COLORS

    s = LandCoverScheme.default()
    assert s.palette() == tuple(DEFAULT_LC_COLORS.values())
    assert s.color_by_class() == dict(DEFAULT_LC_COLORS)
    assert s.code_ordered_names == DEFAULT_LC_CLASS_NAMES
    # both length 7 by construction in tables.py — a mismatch would be a real bug
    assert s.code_to_name_start() == dict(
        zip(DEFAULT_LC_CODES, DEFAULT_LC_CLASS_NAMES, strict=True)
    )


def test_scheme_is_frozen() -> None:
    s = LandCoverScheme.default()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.start_names = ()  # type: ignore[misc]


# --------------------------------------------------------------------------
# read_matrix_csv
# --------------------------------------------------------------------------
def test_read_matrix_csv_handles_the_crlf_golden(golden_rows: list[list[str]]) -> None:
    assert len(golden_rows) == 15
    assert {len(r) for r in golden_rows} == {15}
    assert golden_rows[0][:3] == ["Land cover", "2015", "Native forest"]
    assert golden_rows[1][:3] == ["2000", "Code", "10"]
    assert golden_rows[-1][0] == "Other Land"
    assert all(not cell.endswith("\r") for row in golden_rows for cell in row)


def test_read_matrix_csv_returns_plain_strings() -> None:
    rows = read_matrix_csv("a,b\nc,d\n")
    assert rows == [["a", "b"], ["c", "d"]]


def test_read_matrix_csv_handles_quoted_commas_and_embedded_newlines() -> None:
    """The stated reason for going through ``csv`` rather than ``str.splitlines``
    (module docstring): a quoted field can hide a comma or a newline that must not
    split the row."""
    text = 'a,"b, with a comma","c\nspanning two lines"\nd,e,f\n'
    rows = read_matrix_csv(text)
    assert rows == [["a", "b, with a comma", "c\nspanning two lines"], ["d", "e", "f"]]


# --------------------------------------------------------------------------
# parse_custom_matrix_csv — the golden
# --------------------------------------------------------------------------
def test_golden_csv_parses_to_the_expected_scheme(golden_rows: list[list[str]]) -> None:
    s = parse_custom_matrix_csv(golden_rows)
    names = (
        "Native forest",
        "Exotic forest",
        "Native grassland",
        "Improve pasture",
        "Managed parkland",
        "Plantation",
        "Cereals",
        "Horticulture",
        "Wetland-permanent",
        "Wetland-ephemeral",
        "Coastal wetland",
        "Settlements",
        "Other Land",
    )
    codes = tuple(range(10, 23))
    assert s.is_custom is True
    assert s.start_names == names
    assert s.end_names == names
    assert s.start_codes == codes
    assert s.end_codes == codes
    assert len(s.matrix.rows) == 13
    assert all(len(r) == 13 for r in s.matrix.rows)
    assert s.matrix.rows[0] == (0, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1)
    assert s.matrix.rows[-1] == (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, -1, 0)
    assert s.matrix.flatten()[:3] == (0, -1, -1)
    assert len(s.matrix.flatten()) == 169


def test_golden_combinations_and_labels(golden_rows: list[list[str]]) -> None:
    s = parse_custom_matrix_csv(golden_rows)
    assert len(s.class_combinations) == 169
    assert s.class_combinations[:5] == (1010, 1011, 1012, 1013, 1014)
    assert s.class_combinations[-1] == 2222
    assert s.combination_labels[0] == "Native forest_Native forest"
    assert s.combination_labels[-1] == "Other Land_Other Land"
    assert s.code_to_name_start()[13] == "Improve pasture"


def test_golden_palette_matches_the_legacy_sampler(golden_rows: list[list[str]]) -> None:
    """transcribed from indicator_model.py:246-266 — random.seed(100) then
    random.sample over matplotlib's cnames values."""
    s = parse_custom_matrix_csv(golden_rows)
    assert s.palette() == tuple(random.Random(100).sample(CSS4_HEX, 13))
    colours = s.color_by_class()
    assert list(colours) == list(s.code_ordered_names)
    assert colours["Native forest"] == "#2F4F4F"
    assert colours["Exotic forest"] == "#B0E0E6"


def test_palette_does_not_disturb_the_process_rng(golden_rows: list[list[str]]) -> None:
    random.seed(1234)
    before = random.random()
    random.seed(1234)
    parse_custom_matrix_csv(golden_rows).palette()
    assert random.random() == before


# --------------------------------------------------------------------------
# CSV order vs code order
# --------------------------------------------------------------------------
OUT_OF_ORDER = (
    "Land cover,2015,Cane,Apple,Bean\r\n"
    "2000,Code,30,10,20\r\n"
    "Cane,30,0,1,-1\r\n"
    "Apple,10,-1,0,1\r\n"
    "Bean,20,1,-1,0"
)


def test_combinations_follow_csv_order_but_names_sort_by_code() -> None:
    s = parse_custom_matrix_csv(read_matrix_csv(OUT_OF_ORDER))

    # CSV order is preserved everywhere the graph depends on it
    assert s.start_names == ("Cane", "Apple", "Bean")
    assert s.start_codes == (30, 10, 20)
    assert s.end_codes == (30, 10, 20)
    assert s.class_combinations == (
        3030,
        3010,
        3020,
        1030,
        1010,
        1020,
        2030,
        2010,
        2020,
    )
    assert s.combination_labels[:3] == ("Cane_Cane", "Cane_Apple", "Cane_Bean")
    assert s.matrix.flatten() == (0, 1, -1, -1, 0, 1, 1, -1, 0)

    # colours are assigned in code order (indicator_model.py:251-262)
    assert s.code_ordered_names == ("Apple", "Bean", "Cane")
    assert s.palette() == tuple(random.Random(100).sample(CSS4_HEX, 3))
    assert s.color_by_class() == {
        "Apple": "#2F4F4F",
        "Bean": "#B0E0E6",
        "Cane": "#DDA0DD",
    }
    # code_to_name_start pairs by position, not by sort (run_15_3_1.py:266)
    assert s.code_to_name_start() == {30: "Cane", 10: "Apple", 20: "Bean"}


# --------------------------------------------------------------------------
# the [^a-zA-Z -]+ scrub, character for character
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,scrubbed",
    [
        ("  Native forest  ", "Native forest"),
        ("Wetland-permanent", "Wetland-permanent"),
        ("Class_1", "Class"),
        ("Cropland (rainfed)", "Cropland rainfed"),
        ("Zone 3", "Zone "),
        ("a1b2c3", "abc"),
        ("Tree/Shrub", "TreeShrub"),
        ("Bosque nativo", "Bosque nativo"),
        ("Bosque nátivo", "Bosque ntivo"),
        # "50%" is stripped as one disallowed run, but the space it bordered was
        # interior at strip() time, so it survives as a new leading space — this
        # is the legacy behaviour (indicator_model.py:186), not a typo.
        ("50% forest", " forest"),
        ("A  B", "A  B"),
        ("---", "---"),
        ("...", ""),
    ],
)
def test_name_scrub_is_character_for_character(raw: str, scrubbed: str) -> None:
    """transcribed from indicator_model.py:186-187 / :196-197:

        pattern = re.compile(r"[^a-zA-Z -]+")
        lc_class = [re.sub(pattern, "", x.strip()) for x in lc_class]

    Underscores, digits, punctuation and accented letters go; ASCII letters,
    spaces and hyphens stay. `.strip()` runs *before* the substitution, so leading
    and trailing spaces around the surviving text are removed but interior runs
    are not collapsed.
    """
    rows = [
        ["Land cover", "2015", raw],
        ["2000", "Code", "10"],
        [raw, "10", "0"],
    ]
    s = parse_custom_matrix_csv(rows)
    assert s.end_names == (scrubbed,)
    assert s.start_names == (scrubbed,)


# --------------------------------------------------------------------------
# malformed input — one fixture per rule
# --------------------------------------------------------------------------
def test_too_few_rows_raises() -> None:
    with pytest.raises(CustomMatrixError, match="at least three rows"):
        parse_custom_matrix_csv([["Land cover", "2015", "A"], ["2000", "Code", "10"]])


def test_no_class_columns_raises() -> None:
    with pytest.raises(CustomMatrixError, match="no land cover classes"):
        parse_custom_matrix_csv([["Land cover", "2015"], ["2000", "Code"], ["A", "10"]])


def test_non_integer_end_code_raises() -> None:
    rows = [["Land cover", "2015", "A"], ["2000", "Code", "ten"], ["A", "10", "0"]]
    with pytest.raises(CustomMatrixError, match="end class code"):
        parse_custom_matrix_csv(rows)


def test_non_integer_start_code_raises() -> None:
    rows = [["Land cover", "2015", "A"], ["2000", "Code", "10"], ["A", "x10", "0"]]
    with pytest.raises(CustomMatrixError, match="start class code"):
        parse_custom_matrix_csv(rows)


def test_header_and_code_row_length_mismatch_raises() -> None:
    rows = [["Land cover", "2015", "A", "B"], ["2000", "Code", "10"], ["A", "10", "0", "0"]]
    with pytest.raises(CustomMatrixError, match=r"class names .* class codes"):
        parse_custom_matrix_csv(rows)


def test_ragged_matrix_row_raises() -> None:
    rows = [
        ["Land cover", "2015", "A", "B"],
        ["2000", "Code", "10", "20"],
        ["A", "10", "0", "1"],
        ["B", "20", "0"],
    ]
    with pytest.raises(CustomMatrixError, match="row 2"):
        parse_custom_matrix_csv(rows)


def test_non_integer_matrix_cell_raises() -> None:
    rows = [["Land cover", "2015", "A"], ["2000", "Code", "10"], ["A", "10", "yes"]]
    with pytest.raises(CustomMatrixError, match="transition value"):
        parse_custom_matrix_csv(rows)


def test_short_data_row_raises() -> None:
    rows = [["Land cover", "2015", "A"], ["2000", "Code", "10"], ["A"]]
    with pytest.raises(CustomMatrixError, match="row 1"):
        parse_custom_matrix_csv(rows)
