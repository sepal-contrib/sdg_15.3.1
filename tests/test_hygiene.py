"""Tier 0 guard 4 — the AST hygiene walk: the legacy defects that must not be
re-introduced, and the UI boundary the domain may not cross.

Runs over the domain package and, once it exists, the app package. Every rule is
also exercised against a planted violation, so the guard cannot silently rot into
a no-op the day someone reorders the AST.
"""

from __future__ import annotations

import pytest
from hygiene_rules import check_source, iter_domain_sources


def test_the_walk_actually_found_the_domain() -> None:
    """An empty parametrize passes vacuously, so pin that the walk found sources.

    Without this, a rename of ``sdg1531/`` (or a bug in ``ROOTS``) would turn
    guard 4 into a silent no-op instead of a failure.
    """
    paths = [rel for rel, _ in iter_domain_sources()]
    assert "sdg1531/__init__.py" in paths, paths
    assert len(paths) == len(set(paths)), paths


_DOMAIN_SOURCES = iter_domain_sources()
# guards this parametrize specifically: an empty list would make the test below pass
# vacuously even if test_the_walk_actually_found_the_domain were ever deleted or skipped.
assert _DOMAIN_SOURCES, "iter_domain_sources() found nothing; guard 4 would run over zero files"


@pytest.mark.parametrize(
    "rel_path,source",
    _DOMAIN_SOURCES,
    ids=lambda v: v if isinstance(v, str) and v.endswith(".py") else "",
)
def test_domain_source_is_clean(rel_path: str, source: str) -> None:
    violations = check_source(rel_path, source)
    assert violations == [], "\n".join(str(v) for v in violations)


def _rules(source: str, rel_path: str = "sdg1531/probe.py") -> set[str]:
    return {v.rule for v in check_source(rel_path, source)}


def test_star_import_is_rejected() -> None:
    assert "star-import" in _rules("__all__ = []\nfrom os.path import *\n")


def test_missing_dunder_all_is_rejected() -> None:
    assert "missing-dunder-all" in _rules("def f() -> int:\n    return 1\n")


def test_docstring_only_module_needs_no_dunder_all() -> None:
    assert _rules('"""nothing here yet."""\n') == set()


def test_globals_subscript_is_rejected() -> None:
    src = '__all__ = ["f"]\ndef f(name):\n    return globals()[name]\n'
    assert "globals-subscript" in _rules(src)


@pytest.mark.parametrize("param", ["output", "model", "aoi_model", "alert"])
def test_widget_bag_parameters_are_rejected(param: str) -> None:
    src = f'__all__ = ["f"]\ndef f(a, {param}=None):\n    return a\n'
    assert "banned-param" in _rules(src)


def test_private_helper_may_keep_a_banned_parameter() -> None:
    # underscore-private helpers are the escape hatch; the rule is about the API
    src = "__all__ = []\ndef _f(a, model=None):\n    return a\n"
    assert "banned-param" not in _rules(src)


@pytest.mark.parametrize(
    "expr", ["x.getInfo()", "fc.getDownloadURL(filetype='geojson')", "urlopen(url)", "print('hi')"]
)
def test_blocking_and_noisy_calls_are_rejected(expr: str) -> None:
    src = f'__all__ = ["f"]\ndef f(x, fc, url, urlopen):\n    return {expr}\n'
    assert "banned-call" in _rules(src)


def test_filesystem_access_is_rejected() -> None:
    src = '__all__ = ["f"]\nfrom pathlib import Path\ndef f():\n    return Path.home()\n'
    assert "filesystem" in _rules(src)


@pytest.mark.parametrize("expr", ["open(p)", "p.open()"])
def test_open_is_rejected_in_both_call_forms(expr: str) -> None:
    # open() was only banned as a bare call; Path(...).open() passed all four guards
    src = f'__all__ = ["f"]\ndef f(p):\n    return {expr}\n'
    assert "filesystem" in _rules(src)


def test_unrelated_attribute_call_is_not_flagged_as_filesystem() -> None:
    src = '__all__ = ["f"]\ndef f(d):\n    return d.items()\n'
    assert "filesystem" not in _rules(src)


def test_urlopen_attribute_form_is_rejected_like_the_bare_call() -> None:
    src = '__all__ = ["f"]\ndef f(request, url):\n    return request.urlopen(url)\n'
    assert "banned-call" in _rules(src)


def test_similarly_named_attribute_is_not_treated_as_urlopen() -> None:
    src = '__all__ = ["f"]\ndef f(request, url):\n    return request.urlopen_all(url)\n'
    assert "banned-call" not in _rules(src)


def test_export_module_may_write_a_temp_shapefile() -> None:
    src = '__all__ = ["f"]\ndef f(gdf, path):\n    gdf.to_file(path)\n'
    assert "filesystem" not in _rules(src, rel_path="sdg1531/export.py")
    assert "filesystem" in _rules(src, rel_path="sdg1531/stats/decode.py")


def test_export_module_may_read_back_the_zipped_bytes() -> None:
    src = '__all__ = ["f"]\ndef f(path):\n    return path.read_bytes()\n'
    assert "filesystem" not in _rules(src, rel_path="sdg1531/export.py")
    assert "filesystem" in _rules(src, rel_path="sdg1531/stats/decode.py")


def test_export_module_exemption_does_not_cover_every_filesystem_call() -> None:
    # the exemption is for the to_file/read_bytes round trip only, not a blanket
    # pass for sdg1531/export.py
    src = '__all__ = ["f"]\nfrom pathlib import Path\ndef f():\n    return Path.home()\n'
    assert "filesystem" in _rules(src, rel_path="sdg1531/export.py")


def test_module_level_call_is_rejected() -> None:
    src = '__all__ = []\nimport os\nos.makedirs("/tmp/x")\n'
    assert "module-level-call" in _rules(src)


@pytest.mark.parametrize(
    "value",
    [
        '{"a": 1}',
        "[1, 2]",
        "{1, 2}",
        '{k: 1 for k in "ab"}',
        "[n for n in range(3)]",
        "dict(a=1)",
        "list(range(3))",
    ],
)
def test_module_level_mutable_container_is_rejected(value: str) -> None:
    # widget/transition_matrix.py:46 index-assigns into a module-level constant,
    # which under Solara leaks one user's matrix into every other session.
    src = f'__all__ = ["T"]\nT = {value}\n'
    assert "module-level-mutable" in _rules(src)


@pytest.mark.parametrize(
    "value",
    [
        'MappingProxyType({"a": 1})',
        "frozenset({1, 2})",
        "tuple(range(3))",
        "(1, 2, 3)",
        "-32768",
        're.compile(r"x")',
    ],
)
def test_immutable_module_level_constant_is_accepted(value: str) -> None:
    src = f'__all__ = ["T"]\nimport re\nfrom types import MappingProxyType\nT = {value}\n'
    assert "module-level-mutable" not in _rules(src)


@pytest.mark.parametrize("dunder_all", ['("f",)', '["f"]'])
def test_dunder_all_is_never_a_mutable_state_violation(dunder_all: str) -> None:
    src = f"__all__ = {dunder_all}\ndef f() -> int:\n    return 1\n"
    assert "module-level-mutable" not in _rules(src)


def test_dunder_slots_is_never_a_mutable_state_violation() -> None:
    src = '__all__ = ["C"]\nclass C:\n    __slots__ = ["a", "b"]\n'
    assert "module-level-mutable" not in _rules(src)


@pytest.mark.parametrize(
    "value",
    [
        "defaultdict(list)",
        "OrderedDict()",
        "collections.OrderedDict()",
        "Counter()",
        "deque()",
        "bytearray()",
    ],
)
def test_module_level_mutable_factory_is_rejected(value: str) -> None:
    # dict/list/set covered the literal-producing builtins but missed the stdlib
    # factories that produce the same kind of shared, writable container
    src = (
        '__all__ = ["T"]\n'
        "import collections\n"
        "from collections import Counter, OrderedDict, defaultdict, deque\n"
        f"T = {value}\n"
    )
    assert "module-level-mutable" in _rules(src)


def test_namedtuple_factory_is_not_flagged_as_mutable() -> None:
    src = '__all__ = ["Point"]\nfrom collections import namedtuple\nPoint = namedtuple("Point", ["x", "y"])\n'
    assert "module-level-mutable" not in _rules(src)


def test_sorted_call_is_rejected_as_module_level_mutable() -> None:
    src = '__all__ = ["T"]\nT = sorted([3, 1, 2])\n'
    assert "module-level-mutable" in _rules(src)


def test_dict_union_binop_is_rejected_as_module_level_mutable() -> None:
    src = '__all__ = ["T"]\nT = {"a": 1} | {"b": 2}\n'
    assert "module-level-mutable" in _rules(src)


def test_numeric_binop_is_not_flagged_as_mutable() -> None:
    src = '__all__ = ["T"]\nT = 1 + 2\n'
    assert "module-level-mutable" not in _rules(src)


def test_tuple_unpacked_module_level_mutables_are_rejected() -> None:
    src = '__all__ = ["A", "B"]\nA, B = {}, []\n'
    assert "module-level-mutable" in _rules(src)


def test_tuple_unpacked_immutables_are_not_flagged() -> None:
    src = '__all__ = ["A", "B"]\nA, B = (1, 2), (3, 4)\n'
    assert "module-level-mutable" not in _rules(src)


def test_mutable_class_attribute_is_rejected() -> None:
    # a top-level class's own attribute dict is shared across every instance and
    # every importer for the process lifetime — the same defect as a module global
    src = '__all__ = ["C"]\nclass C:\n    DEFAULTS = {}\n'
    assert "module-level-mutable" in _rules(src)


def test_immutable_class_attribute_is_not_flagged() -> None:
    src = '__all__ = ["C"]\nclass C:\n    DEFAULTS = (1, 2)\n'
    assert "module-level-mutable" not in _rules(src)


def test_apply_truth_table_outside_engine_is_rejected() -> None:
    src = '__all__ = ["f"]\ndef f(imgs, table):\n    return apply_truth_table(imgs, table, "b")\n'
    assert "truth-table-leak" in _rules(src, rel_path="sdg1531/stats/requests.py")
    assert "truth-table-leak" not in _rules(src, rel_path="sdg1531/engine/indicator.py")


def test_apply_truth_table_is_allowed_in_single_module_engine_spelling() -> None:
    src = '__all__ = ["f"]\ndef f(imgs, table):\n    return apply_truth_table(imgs, table, "b")\n'
    assert "truth-table-leak" not in _rules(src, rel_path="sdg1531/engine.py")


def test_engine_prefix_match_does_not_leak_into_similarly_named_module() -> None:
    # a naive "startswith sdg1531/engine" would also swallow sdg1531/engineering.py
    src = '__all__ = ["f"]\ndef f(imgs, table):\n    return apply_truth_table(imgs, table, "b")\n'
    assert "truth-table-leak" in _rules(src, rel_path="sdg1531/engineering.py")


def test_replacing_a_resolved_spec_is_rejected() -> None:
    src = (
        '__all__ = ["f"]\n'
        "from dataclasses import replace\n"
        "def f(resolved):\n"
        "    return replace(resolved, analysis_scale=30)\n"
    )
    assert "resolved-replace" in _rules(src)


def test_replacing_a_resolved_spec_by_longer_name_is_rejected() -> None:
    src = (
        '__all__ = ["f"]\n'
        "from dataclasses import replace\n"
        "def f(resolved_spec):\n"
        "    return replace(resolved_spec, analysis_scale=30)\n"
    )
    assert "resolved-replace" in _rules(src)


def test_replacing_a_resolved_spec_via_attribute_access_is_rejected() -> None:
    # ResolvedSpec is normally threaded through as an instance attribute, not a bare
    # local, and the old rule only ever matched an ast.Name
    src = (
        '__all__ = ["f"]\n'
        "from dataclasses import replace\n"
        "class C:\n"
        "    def f(self):\n"
        "        return replace(self.resolved, analysis_scale=30)\n"
    )
    assert "resolved-replace" in _rules(src)


def test_replacing_an_unrelated_object_is_not_flagged() -> None:
    src = (
        '__all__ = ["f"]\n'
        "from dataclasses import replace\n"
        "def f(config):\n"
        "    return replace(config, scale=30)\n"
    )
    assert "resolved-replace" not in _rules(src)


@pytest.mark.parametrize(
    "expr",
    [
        "tempfile.mkdtemp()",
        "tempfile.mkstemp()",
        "tempfile.TemporaryDirectory()",
        "tempfile.NamedTemporaryFile()",
        "tempfile.TemporaryFile()",
        "tempfile.SpooledTemporaryFile()",
    ],
)
def test_temp_spool_is_rejected(expr: str) -> None:
    # the filesystem rule listed mkdir/open/write_text and every other way of
    # naming a path, but not the tempfile entry points, which create a directory
    # or a file without one. sdg1531/export.py became the first module in the
    # domain to use one, and no static guard covered it.
    src = f'__all__ = ["f"]\nimport tempfile\ndef f():\n    return {expr}\n'
    assert "filesystem" in _rules(src)


@pytest.mark.parametrize("expr", ["mkdtemp()", "TemporaryDirectory()", "mkstemp()"])
def test_temp_spool_is_rejected_in_the_imported_form_too(expr: str) -> None:
    src = (
        '__all__ = ["f"]\n'
        "from tempfile import TemporaryDirectory, mkdtemp, mkstemp\n"
        "def f():\n"
        f"    return {expr}\n"
    )
    assert "filesystem" in _rules(src)


def test_export_module_may_spool_the_directory_it_zips() -> None:
    # zonal_shapefile_zip has to give the shapefile driver a directory to write
    # into, and deletes it before returning
    src = '__all__ = ["f"]\nimport tempfile\ndef f():\n    return tempfile.TemporaryDirectory()\n'
    assert "filesystem" not in _rules(src, rel_path="sdg1531/export.py")
    assert "filesystem" in _rules(src, rel_path="sdg1531/stats/decode.py")


def test_the_export_exemption_does_not_cover_every_temp_spool() -> None:
    # the one exemption is the directory; a stray temp FILE left in the spool is
    # exactly the leak the rule is for
    src = '__all__ = ["f"]\nimport tempfile\ndef f():\n    return tempfile.mkstemp()\n'
    assert "filesystem" in _rules(src, rel_path="sdg1531/export.py")
