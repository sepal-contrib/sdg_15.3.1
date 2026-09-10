"""Every hand-maintained roster in the suite, held to what it claims to cover.

A roster is a module-level list of names some test iterates. Three of them have
gone stale on this plan: ``JSON_HALF`` twice, and ``NOTE_MODULES`` once -- and
that one omitted three modules whose sixteen declared divergences never reached
the register, while the test whose docstring says it prevents exactly that stayed
green, because the set it checked against was the set it was derived from. The fix
found for ``NOTE_MODULES`` was to stop writing the roster down and DERIVE it from a
source scan. This file generalises that, in two layers.

**The scan.** :func:`iter_string_rosters` finds every module-level collection of
string constants under ``tests/``. A new one cannot appear without
``ROSTER_ACCOUNTS`` gaining an entry, because the two are compared in both
directions. ``ROSTER_ACCOUNTS`` is itself a hand-maintained roster -- the last one
-- and it is the only kind that cannot rot by omission, since the thing it must
cover is measured rather than remembered.

**The accounts.** Each entry says which of four things the roster is, and a roster
whose claim is checkable is checked here rather than described:

``derived``
    a test recomputes the list from the code it describes and compares. The only
    account that makes staleness impossible.
``both directions``
    an existing test already fails on a missing entry AND on an entry that no
    longer applies. Equivalent in strength to ``derived``; named so the reader can
    go and read it.
``vocabulary``
    a closed list transcribed from something outside this repo -- ``ee``'s
    encoder, the ECharts option schema, the ESRI shapefile format, the libraries
    spec §4 bars. There is nothing in the repo to derive it from, and the honest
    thing is to say so rather than invent a derivation that only restates the list.
``fixture``
    literal test data. It describes nothing but itself, so it cannot be stale.

An account that fits none of those prefixes is rejected, so "accounted for" cannot
degrade into a blank string.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
from collections.abc import Mapping
from pathlib import Path

from _subprocess import run_python
from conftest import REPO_ROOT
from hygiene_rules import FS_EXEMPT_FILES, ROOTS
from test_isolation import JSON_HALF
from test_resolve import RESOLVED_FIELD, SUB_PERIODS
from test_validate import SENSOR_NAMES

from sdg1531.catalog import SENSORS
from sdg1531.resolve import ResolvedSpec
from sdg1531.spec import SubPeriods

SUITE_ROOT = REPO_ROOT / "tests"
EXPORT_ROOTS = ("sdg1531", "tests", "tools")

_ACCOUNT_PREFIXES = ("derived:", "both directions:", "vocabulary:", "fixture:")

# The package inits under `sdg1531/`. They are the three names the ee-free scan
# finds that JSON_HALF does not list, and `test_the_namespace_exclusion_is_still_
# true` re-earns the exclusion on every run: each is a docstring plus an empty
# `__all__`, so there is no code in it that could import anything.
NAMESPACE_PACKAGES = ("sdg1531", "sdg1531.engine", "sdg1531.stats")

# Top-level packages the Tier-0 hygiene walk is not meant to cover. `tests` is the
# suite itself, and `tools` is stage A, which imports the legacy tree on purpose.
NOT_DOMAIN_PACKAGES = ("tests", "tools")

ROSTER_ACCOUNTS: Mapping[str, str] = {
    "tests/_subprocess.py:__all__": "derived: test_every_export_list_matches_its_module",
    "tests/engine/test_context.py:GEOJSON": "fixture: the AOI polygon the context tests build from",
    "tests/engine/test_indicator.py:_BAND_PRESERVING": "vocabulary: ee's encoder -- the nodes that hand a band list through",
    "tests/engine/test_indicator.py:_OPERANDS": "vocabulary: the three band names build_indicator collapses",
    "tests/engine/test_indicator.py:_RECEIVER_ARG": "vocabulary: ee's encoder -- which argument each node carries its receiver in",
    "tests/engine/test_land_cover.py:_RECEIVER_ARG": "vocabulary: ee's encoder -- which argument each node carries its receiver in",
    "tests/engine/test_productivity.py:_RECEIVER_ARG": "vocabulary: ee's encoder -- which argument each node carries its receiver in",
    "tests/engine/test_soc.py:_COMPARISONS": "vocabulary: ee's six Image comparison operators",
    "tests/engine/test_soc.py:_RECEIVER_ARG": "vocabulary: ee's encoder -- which argument each node carries its receiver in",
    "tests/engine/test_water_mask.py:_COMPARISONS": "vocabulary: ee's six Image comparison operators",
    "tests/hygiene_rules.py:BANNED_CALL_ATTRS": "vocabulary: the blocking and noisy calls spec §4 bars from the domain",
    "tests/hygiene_rules.py:BANNED_CALL_NAMES": "vocabulary: the blocking and noisy calls spec §4 bars from the domain",
    "tests/hygiene_rules.py:BANNED_PARAMS": "vocabulary: the widget-bag parameter names spec §7 names",
    "tests/hygiene_rules.py:FS_CALL_ATTRS": "vocabulary: the stdlib's filesystem entry points",
    "tests/hygiene_rules.py:FS_CALL_NAMES": "vocabulary: the stdlib's filesystem entry points",
    "tests/hygiene_rules.py:FS_EXEMPT_CALLS": "vocabulary: the two calls spec D12 allows sdg1531/export.py",
    "tests/hygiene_rules.py:FS_EXEMPT_FILES": "derived: test_every_hygiene_exemption_names_a_file_that_exists",
    "tests/hygiene_rules.py:MUTABLE_BUILTINS": "vocabulary: the stdlib factories that return a fresh mutable container",
    "tests/hygiene_rules.py:MUTABLE_CHECK_EXEMPT_NAMES": "vocabulary: the two attribute lists the interpreter itself reads",
    "tests/hygiene_rules.py:RESOLVED_NAMES": "vocabulary: the spellings a ResolvedSpec is threaded through under",
    "tests/hygiene_rules.py:ROOTS": "derived: test_the_hygiene_walk_covers_every_first_party_package",
    "tests/parity/canonical.py:_BARE_SCOPE_KEY": "vocabulary: ee's four spellings of a scope reference",
    "tests/parity/canonical.py:__all__": "derived: test_every_export_list_matches_its_module",
    "tests/parity/expected_divergences.py:EXPECTED_COMPATIBILITY_DIVERGENCES": "both directions: test_every_compatibility_footprint_names_a_scenario_that_sets_a_flag",
    "tests/parity/expected_divergences.py:EXPECTED_LEGACY_AND_PORT_BOTH_FAIL": "both directions: test_scenario_graphs_match_the_goldens",
    "tests/parity/expected_divergences.py:EXPECTED_LEGACY_ONLY_FAILS": "both directions: test_every_legacy_only_failure_recorded_a_legacy_crash",
    "tests/parity/expected_divergences.py:EXPECTED_OFF_GRAPH": "both directions: test_every_module_divergence_note_is_claimed_by_the_register",
    "tests/parity/expected_divergences.py:__all__": "derived: test_every_export_list_matches_its_module",
    "tests/parity/test_canonical.py:REAL_GRAPHS": "both directions: test_each_real_graph_carries_the_spellings_it_is_recorded_as_carrying",
    "tests/parity/test_canonical.py:_BARE_SPELLINGS": "vocabulary: ee's two bare scope-key spellings",
    "tests/parity/test_canonical.py:_SCOPE_KEY_FIELDS": "vocabulary: every ee field whose string value is a key into `values`",
    "tests/spec_factory.py:__all__": "derived: test_every_export_list_matches_its_module",
    "tests/test_export.py:MANDATORY_MEMBERS": "vocabulary: the ESRI shapefile members a layer cannot be reopened without",
    "tests/test_isolation.py:BANNED_UI": "vocabulary: the UI libraries spec §4 bars from the domain",
    "tests/test_isolation.py:JSON_HALF": "derived: test_the_ee_free_roster_is_every_module_that_imports_without_ee",
    "tests/test_network_smoke.py:AOI_GEOJSON": "fixture: the 10 km box the Tier-6 run computes over",
    "tests/test_plots.py:BAR_SERIES_KEYS": "vocabulary: the ECharts option schema, via ipecharts 1.0.x",
    "tests/test_plots.py:OPTION_KEYS": "vocabulary: the ECharts option schema, via ipecharts 1.0.x",
    "tests/test_plots.py:SANKEY_SERIES_KEYS": "vocabulary: the ECharts option schema, via ipecharts 1.0.x",
    "tests/test_resolve.py:RESOLVED_FIELD": "derived: test_the_sub_period_roster_is_every_sub_period_field",
    "tests/test_resolve.py:SUB_PERIODS": "derived: test_the_sub_period_roster_is_every_sub_period_field",
    "tests/test_rosters.py:NAMESPACE_PACKAGES": "derived: test_the_namespace_exclusion_is_still_true",
    "tests/test_rosters.py:NOT_DOMAIN_PACKAGES": "derived: test_the_hygiene_walk_covers_every_first_party_package",
    "tests/test_rosters.py:ROSTER_ACCOUNTS": "derived: test_every_string_roster_in_the_suite_is_accounted_for",
    "tests/test_rosters.py:_ACCOUNT_PREFIXES": "vocabulary: the four things an account may say, listed in the module docstring",
    "tests/test_rosters.py:EXPORT_ROOTS": "derived: test_every_export_list_matches_its_module",
    "tests/test_stats_requests.py:_LEGACY_LABEL_TABLES": "vocabulary: the four dicts parameter/matrix.py:30-47 names",
    "tests/test_stats_requests.py:_RECEIVER_ARG": "vocabulary: ee's encoder -- which argument each node carries its receiver in",
    "tests/test_validate.py:SENSOR_NAMES": "derived: test_the_sensor_sample_names_real_sensors",
    "tests/test_workflows.py:APP_LAYER_STEPS": "derived: test_the_app_layer_checks_are_intact",
    "tests/test_workflows.py:_SUPPRESSORS": "vocabulary: the shell spellings that swallow a command's exit code",
}


# --- the scan -----------------------------------------------------------------


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _string_elements(value: ast.expr) -> list[ast.expr] | None:
    """The elements of ``value`` when every one of them is a string literal.

    Covers the four literal containers, the ``frozenset({...})`` / ``tuple([...])``
    wrappings, and a dict, whose KEYS are the roster (``RESOLVED_FIELD`` is keyed
    on sub-period names). ``None`` when ``value`` is anything else, or when one
    element is not a plain string -- a mixed container is not a roster of names.
    """
    elements: list[ast.expr] | None = None
    minimum = 1
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        elements = list(value.elts)
    elif (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in ("frozenset", "set", "tuple", "list")
        and value.args
        and isinstance(value.args[0], (ast.Tuple, ast.List, ast.Set))
    ):
        elements = list(value.args[0].elts)
    elif isinstance(value, ast.Dict):
        # a one-key dict is a lookup, not a roster; a one-element tuple can still be
        # a roster of exemptions (FS_EXEMPT_FILES is exactly that)
        elements = [key for key in value.keys if key is not None]
        minimum = 2
    if elements is None or len(elements) < minimum:
        return None
    if not all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in elements):
        return None
    return elements


def iter_string_rosters() -> dict[str, int]:
    """``{"tests/x.py:NAME": element count}`` for every module-level string roster."""
    found: dict[str, int] = {}
    for path in sorted(SUITE_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if not names or node.value is None:
                continue
            elements = _string_elements(node.value)
            if elements is not None:
                found[f"{rel}:{names[0]}"] = len(elements)
    return found


def test_the_scan_still_finds_rosters() -> None:
    """The scan is what keeps ROSTER_ACCOUNTS honest, so an empty one is fatal.

    Naming two known rosters pins the two shapes it has to keep matching: a tuple
    of module names and a frozenset built from a literal.
    """
    found = iter_string_rosters()

    assert len(found) > 30, found
    assert found["tests/test_isolation.py:JSON_HALF"] == len(JSON_HALF)
    assert "tests/hygiene_rules.py:FS_EXEMPT_FILES" in found


def test_every_string_roster_in_the_suite_is_accounted_for() -> None:
    found = set(iter_string_rosters())
    accounted = set(ROSTER_ACCOUNTS)

    unaccounted = sorted(found - accounted)
    assert unaccounted == [], (
        f"rosters with no account: {unaccounted}. Say which of "
        f"{[p.rstrip(':') for p in _ACCOUNT_PREFIXES]} each one is."
    )
    stale = sorted(accounted - found)
    assert stale == [], f"accounts for rosters that no longer exist: {stale}"


def test_every_account_names_a_test_that_exists() -> None:
    """A ``derived``/``both directions`` account is a pointer, and a pointer at
    nothing reads as coverage that is not there. Two of the accounts below named
    tests that did not exist when they were first written -- the same defect the
    register entries in ``expected_divergences.py`` carry, one level up.

    Exactly one definition, not at least one: a name two files define does not say
    which test does the checking.
    """
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(SUITE_ROOT.rglob("test_*.py"))
    )
    problems = []
    for key, account in ROSTER_ACCOUNTS.items():
        prefix, _, cited = account.partition(":")
        if prefix not in ("derived", "both directions"):
            continue
        name = cited.strip()
        count = len(re.findall(rf"^\s*(?:async )?def {re.escape(name)}\(", sources, re.MULTILINE))
        if count != 1:
            problems.append(f"{key} names {name}, defined {count} times")

    assert problems == [], problems


def test_every_account_says_one_of_the_four_things() -> None:
    vague = sorted(
        key for key, account in ROSTER_ACCOUNTS.items() if not account.startswith(_ACCOUNT_PREFIXES)
    )

    assert vague == [], f"accounts that classify nothing: {vague}"


# --- the derivations ----------------------------------------------------------

_EE_FREE_SCAN = """
import importlib, json, pkgutil, sys


class _Blocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] == "ee":
            raise ImportError("ee is blocked for this scan")
        return None


sys.meta_path.insert(0, _Blocker())

import sdg1531

names = ["sdg1531"] + sorted(m.name for m in pkgutil.walk_packages(sdg1531.__path__, "sdg1531."))
free = []
for name in names:
    try:
        importlib.import_module(name)
    except ImportError:
        continue
    free.append(name)
print(json.dumps({"scanned": names, "free": free}))
"""


def test_the_ee_free_roster_is_every_module_that_imports_without_ee() -> None:
    """JSON_HALF, measured rather than remembered.

    It went stale twice: Task 15 had to add ``sdg1531.ports`` and
    ``sdg1531.stats.decode``, Task 16 its own two. A module that belongs on it and
    is not on it is simply never tested, and nothing says so. This imports every
    module under ``sdg1531/`` with ``ee`` blocked and compares the set that
    succeeds -- so a new ee-free module joins the roster by existing.
    """
    proc = run_python(_EE_FREE_SCAN)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)

    assert len(payload["scanned"]) > 20, payload["scanned"]
    assert set(payload["free"]) == set(JSON_HALF) | set(NAMESPACE_PACKAGES), {
        "missing from JSON_HALF": sorted(
            set(payload["free"]) - set(JSON_HALF) - set(NAMESPACE_PACKAGES)
        ),
        "listed but not ee-free": sorted(set(JSON_HALF) - set(payload["free"])),
    }


def test_the_namespace_exclusion_is_still_true() -> None:
    """The three names the scan finds that JSON_HALF does not list.

    They are excluded because there is nothing in them: a docstring and an empty
    ``__all__``. That is re-checked here rather than asserted in a comment, so the
    day one of them grows an import the exclusion stops being free.
    """
    for dotted in NAMESPACE_PACKAGES:
        path = REPO_ROOT / Path(*dotted.split(".")) / "__init__.py"
        body = [
            node
            for node in ast.parse(path.read_text(encoding="utf-8")).body
            if not _is_docstring(node)
        ]

        for node in body:
            if isinstance(node, ast.ImportFrom):
                assert node.module == "__future__", f"{dotted} imports {node.module}"
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                assert all(isinstance(t, ast.Name) and t.id == "__all__" for t in targets), dotted
                assert isinstance(node.value, ast.Tuple) and not node.value.elts, (
                    f"{dotted}'s __all__ is no longer empty"
                )
            else:
                raise AssertionError(f"{dotted}/__init__.py is no longer empty: {ast.dump(node)}")


def test_the_hygiene_walk_covers_every_first_party_package() -> None:
    """ROOTS decides what Tier-0 guard 4 reads, so a package it omits is unguarded.

    One-directional on purpose: ``app`` is on ROOTS and does not exist yet, and
    ``iter_domain_sources`` skips a missing root. What must not happen is a package
    landing under a name nobody added -- an app package called anything other than
    ``app`` would be walked by nothing and this is what says so.
    """
    packages = {
        path.name
        for path in REPO_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith(".") and (path / "__init__.py").is_file()
    }
    uncovered = sorted(packages - set(NOT_DOMAIN_PACKAGES) - set(ROOTS))

    assert uncovered == [], f"first-party packages the hygiene walk never reads: {uncovered}"


def test_every_hygiene_exemption_names_a_file_that_exists() -> None:
    """An exemption for a path that has moved is dead text that reads as coverage."""
    missing = sorted(rel for rel in FS_EXEMPT_FILES if not (REPO_ROOT / rel).is_file())

    assert missing == [], f"filesystem exemptions for files that do not exist: {missing}"


def test_the_sub_period_roster_is_every_sub_period_field() -> None:
    """SUB_PERIODS drives a parametrize, so a sub-period missing from it is a
    sub-period nothing tests. Both it and the ResolvedSpec field map are read off
    the dataclasses rather than typed out."""
    declared = tuple(f.name for f in dataclasses.fields(SubPeriods) if f.name != "overall")
    resolved_fields = {f.name for f in dataclasses.fields(ResolvedSpec)}

    assert declared == SUB_PERIODS
    assert set(RESOLVED_FIELD) == set(declared)
    assert set(RESOLVED_FIELD.values()) <= resolved_fields, sorted(
        set(RESOLVED_FIELD.values()) - resolved_fields
    )


def test_the_sensor_sample_names_real_sensors() -> None:
    """A sample, not a complete roster -- but a sample of names the catalogue does
    not have would exercise the refusal path while claiming to exercise the
    accepting one."""
    unknown = sorted(set(SENSOR_NAMES) - set(SENSORS))

    assert unknown == [], f"sensor names the catalogue does not know: {unknown}"


# --- the export lists ---------------------------------------------------------


def _defined_public_names(tree: ast.Module) -> set[str]:
    """Public names this module DEFINES: assignments, defs, classes, type aliases."""
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            found |= {t.id for t in targets if isinstance(t, ast.Name) and not t.id.startswith("_")}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                found.add(node.name)
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            if not node.name.id.startswith("_"):
                found.add(node.name.id)
    return found


def _bound_names(tree: ast.Module) -> set[str]:
    """Every module-level name, imports included -- what ``import *`` could reach."""
    found = _defined_public_names(tree)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found |= {alias.asname or alias.name.split(".")[0] for alias in node.names}
    return found


def _declared_exports(tree: ast.Module) -> set[str] | None:
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            value = node.value
            if isinstance(value, (ast.Tuple, ast.List)):
                return {e.value for e in value.elts if isinstance(e, ast.Constant)}
    return None


def test_every_export_list_matches_its_module() -> None:
    """``__all__`` is the roster every module keeps, and the hygiene walk requires
    one. A public name missing from it is invisible to ``import *``; a name in it
    that the module does not have breaks ``import *`` outright. This found
    ``sdg1531/resolve.py`` exporting three of its six public names."""
    checked = 0
    problems = []
    for root in EXPORT_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            declared = _declared_exports(tree)
            if declared is None:
                continue
            checked += 1
            rel = path.relative_to(REPO_ROOT).as_posix()
            missing = sorted(_defined_public_names(tree) - declared)
            dangling = sorted(declared - _bound_names(tree))
            if missing:
                problems.append(f"{rel}: public but not exported: {missing}")
            if dangling:
                problems.append(f"{rel}: exported but not defined or imported: {dangling}")

    assert checked > 20, f"only {checked} modules declare __all__; the walk found nothing"
    assert problems == [], "\n".join(problems)
