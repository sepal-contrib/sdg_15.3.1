"""Every hand-maintained roster in the suite, held to what it claims to cover.

A roster is a module-level list of names some test iterates. Three of them have
gone stale on this plan: ``JSON_HALF`` twice, and ``NOTE_MODULES`` once -- and
that one omitted three modules whose sixteen declared divergences never reached
the register, while the test whose docstring says it prevents exactly that stayed
green, because the set it checked against was the set it was derived from. The fix
found for ``NOTE_MODULES`` was to stop writing the roster down and DERIVE it from a
source scan. This file generalises that, in two layers.

**The scan.** :func:`iter_string_rosters` finds every collection of string
constants -- or of tuples of them, a composite-key roster such as ``(path, call
name)`` pairs -- assigned at module level or in a class body under ``tests/``: the
four literal containers, the ``frozenset({...})`` wrappings, a dict's KEYS, and any
combination of those built with an operator or a ``*`` spread. A roster in one of
those shapes cannot appear without ``ROSTER_ACCOUNTS`` gaining an entry, because
the two are compared in both directions. A roster assembled some other way -- by a
call this does not know, or by a comprehension -- is outside the scan; there is no
such roster today, and the claim is worth exactly the shapes it covers. It covered
one shape fewer until fix round 1, where a one-key dict was read as a lookup
rather than a roster: that exemption hid ``EXPECTED_NORMALISATIONS`` and
``HELD_CONSTANT``, two hand-maintained parity registers, from the scan written
because hand-maintained rosters go stale. It covered one shape fewer again at the
app layer's own fix round 1: a frozenset of 2-tuples (``MODULE_LEVEL_CALL_EXEMPT``)
was invisible for the same reason -- an element that is not itself a bare string
was read as "not a roster" -- and a wholly bogus entry in it passed 883 tests
green.

``ROSTER_ACCOUNTS`` is itself a hand-maintained roster -- the last one -- and it is
the only kind that cannot rot by omission, since the thing it must cover is
measured rather than remembered.

**The accounts.** Each entry says which of five things the roster is, and a roster
whose claim is checkable is checked here rather than described:

``derived``
    a test recomputes the list from the code it describes and compares. The only
    account that makes staleness impossible.
``both directions``
    an existing test already fails on a missing entry AND on an entry that no
    longer applies. Equivalent in strength to ``derived``; named so the reader can
    go and read it.
``one direction``
    an existing test fails on one of those two and not the other -- typically it
    checks every entry still applies, while nothing requires a new one to be
    added. Named separately because it is weaker and reads identically otherwise:
    five accounts here said ``derived`` on the strength of a test that only
    CONSUMED the roster, two of them circularly, so narrowing the roster narrowed
    its own check and the account went on vouching for it.
``vocabulary``
    a closed list transcribed from something outside this repo -- ``ee``'s
    encoder, the ECharts option schema, the ESRI shapefile format, the UI libraries
    the domain bars. There is nothing in the repo to derive it from, and the honest
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

import pytest
from _subprocess import run_python
from conftest import REPO_ROOT
from hygiene_rules import FS_EXEMPT_FILES, MODULE_LEVEL_CALL_EXEMPT, ROOTS
from test_isolation import JSON_HALF
from test_resolve import RESOLVED_FIELD, SUB_PERIODS
from test_validate import SENSOR_NAMES

from sdg1531.catalog import SENSORS
from sdg1531.resolve import ResolvedSpec
from sdg1531.spec import SubPeriods

SUITE_ROOT = REPO_ROOT / "tests"
EXPORT_ROOTS = ("sdg1531", "tests", "tools", "app")

_ACCOUNT_PREFIXES = (
    "derived:",
    "both directions:",
    "one direction:",
    "vocabulary:",
    "fixture:",
)

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
    "tests/app/render_helpers.py:__all__": "derived: test_every_export_list_matches_its_module",
    "tests/app/test_legacy_freeze.py:FROZEN": "vocabulary: the component/ subtrees tools/dump_legacy_graphs.py and tools/to_legacy_model.py import (component/scripts, component/model) plus those two modules' own upstream imports (component/parameter, component/message) -- a second scanner reading the same import graph would only restate this one",
    "tests/app/test_scaffolding.py:_UNTRANSLATED_FR_KEYS": "both directions: test_the_catalogue_is_valid",
    "tests/engine/test_context.py:GEOJSON": "fixture: the AOI polygon the context tests build from",
    "tests/engine/test_indicator.py:_BAND_PRESERVING": "vocabulary: ee's encoder -- the nodes that hand a band list through",
    "tests/engine/test_indicator.py:_OPERANDS": "vocabulary: the three band names build_indicator collapses",
    "tests/engine/test_indicator.py:_RECEIVER_ARG": "vocabulary: ee's encoder -- which argument each node carries its receiver in",
    "tests/engine/test_land_cover.py:_RECEIVER_ARG": "vocabulary: ee's encoder -- which argument each node carries its receiver in",
    "tests/engine/test_productivity.py:_RECEIVER_ARG": "vocabulary: ee's encoder -- which argument each node carries its receiver in",
    "tests/engine/test_soc.py:_COMPARISONS": "vocabulary: ee's six Image comparison operators",
    "tests/engine/test_soc.py:_RECEIVER_ARG": "vocabulary: ee's encoder -- which argument each node carries its receiver in",
    "tests/engine/test_water_mask.py:_COMPARISONS": "vocabulary: ee's six Image comparison operators",
    "tests/hygiene_rules.py:BANNED_CALL_ATTRS": "vocabulary: the blocking and noisy calls the domain bars",
    "tests/hygiene_rules.py:BANNED_CALL_NAMES": "vocabulary: the blocking and noisy calls the domain bars",
    "tests/hygiene_rules.py:BANNED_PARAMS": "vocabulary: the legacy widget-bag parameter names",
    "tests/hygiene_rules.py:FS_CALL_ATTRS": "vocabulary: the stdlib's filesystem entry points",
    "tests/hygiene_rules.py:FS_CALL_NAMES": "vocabulary: the stdlib's filesystem entry points",
    "tests/hygiene_rules.py:FS_EXEMPT_CALLS": "vocabulary: the two calls sdg1531/export.py is allowed",
    "tests/hygiene_rules.py:FS_EXEMPT_FILES": "one direction: test_every_hygiene_exemption_names_a_file_that_exists",
    "tests/hygiene_rules.py:_TEMP_SPOOLS": "vocabulary: the tempfile entry points that put something on disk",
    "tests/hygiene_rules.py:MODULE_LEVEL_CALL_EXEMPT": "both directions: test_every_module_level_call_exemption_names_a_real_call",
    "tests/hygiene_rules.py:MUTABLE_BUILTINS": "vocabulary: the stdlib factories that return a fresh mutable container",
    "tests/hygiene_rules.py:MUTABLE_CHECK_EXEMPT_NAMES": "vocabulary: the two attribute lists the interpreter itself reads",
    "tests/hygiene_rules.py:RESOLVED_NAMES": "vocabulary: the spellings a ResolvedSpec is threaded through under",
    "tests/hygiene_rules.py:ROOTS": "derived: test_the_hygiene_walk_covers_every_first_party_package",
    "tests/parity/canonical.py:_BARE_SCOPE_KEY": "vocabulary: ee's four spellings of a scope reference",
    "tests/parity/canonical.py:__all__": "derived: test_every_export_list_matches_its_module",
    "tests/parity/expected_divergences.py:EXPECTED_COMPATIBILITY_DIVERGENCES": "both directions: test_every_compatibility_footprint_names_a_scenario_that_sets_a_flag",
    "tests/parity/expected_divergences.py:EXPECTED_LEGACY_AND_PORT_BOTH_FAIL": "both directions: test_scenario_graphs_match_the_goldens",
    "tests/parity/expected_divergences.py:EXPECTED_LEGACY_ONLY_FAILS": "both directions: test_every_legacy_only_failure_recorded_a_legacy_crash",
    "tests/parity/expected_divergences.py:EXPECTED_NORMALISATIONS": "both directions: test_every_module_divergence_note_is_claimed_by_the_register",
    "tests/parity/expected_divergences.py:EXPECTED_OFF_GRAPH": "both directions: test_every_module_divergence_note_is_claimed_by_the_register",
    "tests/parity/expected_divergences.py:HELD_CONSTANT": "one direction: test_every_held_constant_entry_names_tests_that_exist",
    "tests/parity/expected_divergences.py:__all__": "derived: test_every_export_list_matches_its_module",
    "tests/parity/test_canonical.py:REAL_GRAPHS": "both directions: test_each_real_graph_carries_the_spellings_it_is_recorded_as_carrying",
    "tests/parity/test_canonical.py:_BARE_SPELLINGS": "vocabulary: ee's two bare scope-key spellings",
    "tests/parity/test_canonical.py:_SCOPE_KEY_FIELDS": "vocabulary: every ee field whose string value is a key into `values`",
    "tests/spec_factory.py:__all__": "derived: test_every_export_list_matches_its_module",
    "tests/test_constants.py:COLOUR_MODULES": "both directions: test_the_domains_colours_live_in_the_two_colour_modules",
    "tests/test_export.py:MANDATORY_MEMBERS": "vocabulary: the ESRI shapefile members a layer cannot be reopened without",
    "tests/test_isolation.py:BANNED_UI": "vocabulary: the UI libraries the domain bars",
    "tests/test_isolation.py:JSON_HALF": "derived: test_the_ee_free_roster_is_every_module_that_imports_without_ee",
    "tests/test_naming.py:_SENSOR_NAMES": "fixture: the run_label fuzz's sample -- spread from the catalogue's own SENSORS, plus one name it does not know",
    "tests/test_network_smoke.py:AOI_GEOJSON": "fixture: the 10 km box the Tier-6 run computes over",
    "tests/test_plots.py:BAR_SERIES_KEYS": "vocabulary: the ECharts option schema, via ipecharts 1.0.x",
    "tests/test_plots.py:OPTION_KEYS": "vocabulary: the ECharts option schema, via ipecharts 1.0.x",
    "tests/test_plots.py:SANKEY_SERIES_KEYS": "vocabulary: the ECharts option schema, via ipecharts 1.0.x",
    "tests/test_resolve.py:RESOLVED_FIELD": "derived: test_the_sub_period_roster_is_every_sub_period_field",
    "tests/test_resolve.py:SUB_PERIODS": "derived: test_the_sub_period_roster_is_every_sub_period_field",
    "tests/test_rosters.py:NAMESPACE_PACKAGES": "derived: test_the_namespace_exclusion_is_still_true",
    "tests/test_rosters.py:NOT_DOMAIN_PACKAGES": "both directions: test_the_hygiene_walk_covers_every_first_party_package",
    "tests/test_rosters.py:ROSTER_ACCOUNTS": "derived: test_every_string_roster_in_the_suite_is_accounted_for",
    "tests/test_rosters.py:_ACCOUNT_PREFIXES": "vocabulary: the five things an account may say, listed in the module docstring",
    "tests/test_rosters.py:EXPORT_ROOTS": "derived: test_the_export_walk_covers_every_first_party_package",
    "tests/test_stats_requests.py:_LEGACY_LABEL_TABLES": "vocabulary: the four dicts parameter/matrix.py:30-47 names",
    "tests/test_stats_requests.py:_RECEIVER_ARG": "vocabulary: ee's encoder -- which argument each node carries its receiver in",
    "tests/test_validate.py:SENSOR_NAMES": "one direction: test_the_sensor_sample_names_real_sensors",
    "tests/test_workflows.py:APP_LAYER_STEPS": "one direction: test_the_app_layer_checks_are_intact",
    "tests/test_workflows.py:_REPORTING_FLAGS": "vocabulary: pytest's flags that change how a run is reported, not which tests it selects",
    "tests/test_workflows.py:_SUPPRESSORS": "vocabulary: the shell spellings that swallow a command's exit code",
}


# --- the scan -----------------------------------------------------------------


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_stringy(element: ast.expr) -> bool:
    """A bare string literal, or a tuple made entirely of them.

    A composite-key roster -- ``MODULE_LEVEL_CALL_EXEMPT`` is a ``frozenset`` of
    ``(path, call name)`` pairs -- is still a roster of strings, just structured
    ones; a 2-tuple element was invisible to the plain-``Constant`` check until
    fix round 1, so it never had to earn a ``ROSTER_ACCOUNTS`` entry and a wholly
    bogus entry in it passed the whole suite green.
    """
    if isinstance(element, ast.Constant) and isinstance(element.value, str):
        return True
    if isinstance(element, ast.Tuple):
        return bool(element.elts) and all(
            isinstance(e, ast.Constant) and isinstance(e.value, str) for e in element.elts
        )
    return False


def _string_elements(value: ast.expr) -> list[ast.expr] | None:
    """The elements of ``value`` when every one of them is a string literal, or a
    tuple of them.

    Covers the four literal containers, the ``frozenset({...})`` / ``tuple([...])``
    wrappings, and a dict, whose KEYS are the roster (``RESOLVED_FIELD`` is keyed
    on sub-period names). ``None`` when ``value`` is anything else, or when one
    element is not stringy in that sense -- a mixed container is not a roster of
    names.

    A roster built from another one contributes the literal elements of both
    operands. ``FS_CALL_ATTRS`` is ``frozenset({...}) | _TEMP_SPOOLS``, and a
    scanner that only matched a bare literal would have stopped seeing it the
    moment that rule set was factored -- leaving an account on the books for a
    roster nothing scanned any more. ``|`` was the spelling that hit it and so the
    only one this understood; ``+``, ``-`` and a ``*`` spread are the same shape,
    read the same way, except that the right operand of a difference names what is
    being taken OUT and so contributes nothing.
    """
    if isinstance(value, ast.BinOp):
        left = _string_elements(value.left) or []
        right = [] if isinstance(value.op, ast.Sub) else (_string_elements(value.right) or [])
        return (left + right) or None
    elements: list[ast.expr] | None = None
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
        elements = [key for key in value.keys if key is not None]
    if elements is None:
        return None
    # `(*OTHER, "d")` spreads another roster; the literals beside it are still this
    # one's, and a `**` spread leaves a None key, which is not an element at all
    elements = [e for e in elements if not isinstance(e, ast.Starred)]
    if not elements:
        return None
    if not all(_is_stringy(e) for e in elements):
        return None
    return elements


def _module_rosters(tree: ast.Module) -> dict[str, int]:
    """``{"NAME": element count}`` for every string roster in one parsed module.

    Class bodies are read as well as the module body: a roster is no less
    hand-maintained, and no less iterated, for being an attribute of a class.
    """
    bodies: list[tuple[str, list[ast.stmt]]] = [("", tree.body)]
    bodies += [(f"{n.name}.", n.body) for n in tree.body if isinstance(n, ast.ClassDef)]
    found: dict[str, int] = {}
    for prefix, body in bodies:
        for node in body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if not names or node.value is None:
                continue
            elements = _string_elements(node.value)
            if elements is not None:
                found[f"{prefix}{names[0]}"] = len(elements)
    return found


def iter_string_rosters() -> dict[str, int]:
    """``{"tests/x.py:NAME": element count}`` for every string roster under tests/."""
    found: dict[str, int] = {}
    for path in sorted(SUITE_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found |= {f"{rel}:{name}": count for name, count in _module_rosters(tree).items()}
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
    assert "tests/hygiene_rules.py:FS_CALL_ATTRS" in found


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('X = frozenset({"a"}) | Y', {"X": 1}),
        ('X = ("a", "b") + ("c",)', {"X": 3}),
        ('X = ("a", "b") + OTHER', {"X": 2}),
        ('X = (*OTHER, "d")', {"X": 1}),
        # the right operand of a difference is what is taken OUT, so it is not
        # part of the roster and must not be counted into it
        ('X = frozenset({"a", "b"}) - frozenset({"b"})', {"X": 2}),
        ('X = {"a": 1}', {"X": 1}),
        ('class C:\n    X = ("a", "b")\n', {"C.X": 2}),
        # a composite-key roster: elements are (path, name) pairs, not bare names
        ('X = frozenset({("a", "b")})', {"X": 1}),
        ('X = frozenset({("a", "b"), ("c", "d")})', {"X": 2}),
        # not rosters: a dict assembled from another mapping, a mixed container,
        # and a tuple element with a non-string member
        ("X = {**OTHER}", {}),
        ('X = ("a", 1)', {}),
        ('X = frozenset({("a", 1)})', {}),
    ],
)
def test_the_scan_sees_a_roster_however_it_is_assembled(
    source: str, expected: dict[str, int]
) -> None:
    """The shapes a roster is spelled in, pinned one by one.

    The scan lost sight of ``FS_CALL_ATTRS`` the moment its temp-spool half was
    factored into a shared name, and an account for a roster nothing scans is the
    exact failure this file exists to prevent. ``|`` was generalised then and its
    siblings were not, so ``+``, ``-``, a ``*`` spread and a class body were all
    still invisible -- as was a one-key dict, which hid two live parity registers
    behind the reasoning that a dict that small is a lookup rather than a roster,
    and a composite-key roster, which hid ``MODULE_LEVEL_CALL_EXEMPT`` behind the
    reasoning that an element which is not itself a string is not a roster entry.
    """
    assert _module_rosters(ast.parse(source)) == expected


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
    """A ``derived``/``both directions``/``one direction`` account is a pointer, and
    a pointer at nothing reads as coverage that is not there. Two of the accounts
    below named tests that did not exist when they were first written -- the same
    defect the register entries in ``expected_divergences.py`` carry, one level up.

    Exactly one definition, not at least one: a name two files define does not say
    which test does the checking.
    """
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(SUITE_ROOT.rglob("test_*.py"))
    )
    problems = []
    for key, account in ROSTER_ACCOUNTS.items():
        prefix, _, cited = account.partition(":")
        if prefix not in ("derived", "both directions", "one direction"):
            continue
        name = cited.strip()
        count = len(re.findall(rf"^\s*(?:async )?def {re.escape(name)}\(", sources, re.MULTILINE))
        if count != 1:
            problems.append(f"{key} names {name}, defined {count} times")

    assert problems == [], problems


def test_every_account_says_one_of_the_five_things() -> None:
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

    It went stale twice: ``sdg1531.ports`` and
    ``sdg1531.stats.decode`` had to be added, then two more. A module that belongs on it and
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


def _first_party_packages() -> set[str]:
    """Every top-level package in the repo: a directory with an ``__init__.py``."""
    return {
        path.name
        for path in REPO_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith(".") and (path / "__init__.py").is_file()
    }


def test_the_hygiene_walk_covers_every_first_party_package() -> None:
    """ROOTS decides what Tier-0 guard 4 reads, so a package it omits is unguarded.

    One-directional on ROOTS on purpose: ``app`` is on it and does not exist yet,
    and ``iter_domain_sources`` skips a missing root. What must not happen is a
    package landing under a name nobody added -- an app package called anything
    other than ``app`` would be walked by nothing and this is what says so.

    NOT_DOMAIN_PACKAGES is the SUBTRAHEND, which is the direction that hides
    things: a name added to it takes a package out of this check and takes the
    account vouching for it along too, silently. So each name on it has to be a
    real package that ROOTS does not also claim -- putting ``sdg1531`` on it, which
    exempts the domain from its own hygiene walk, fails here rather than passing
    twelve tests.
    """
    packages = _first_party_packages()
    uncovered = sorted(packages - set(NOT_DOMAIN_PACKAGES) - set(ROOTS))

    assert uncovered == [], f"first-party packages the hygiene walk never reads: {uncovered}"
    absent = sorted(set(NOT_DOMAIN_PACKAGES) - packages)
    assert absent == [], f"exemptions from the walk that are not packages at all: {absent}"
    walked = sorted(set(NOT_DOMAIN_PACKAGES) & set(ROOTS))
    assert walked == [], f"packages exempted from the walk that ROOTS also claims: {walked}"


def test_every_hygiene_exemption_names_a_file_that_exists() -> None:
    """An exemption for a path that has moved is dead text that reads as coverage."""
    missing = sorted(rel for rel in FS_EXEMPT_FILES if not (REPO_ROOT / rel).is_file())

    assert missing == [], f"filesystem exemptions for files that do not exist: {missing}"


def _module_level_call_names(tree: ast.Module) -> set[str]:
    """Every bare-name call made at module level -- what a MODULE_LEVEL_CALL_EXEMPT
    entry has to match, spelled the same way ``hygiene_rules.check_source`` reads it."""
    return {
        node.value.func.id
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    }


def test_every_module_level_call_exemption_names_a_real_call() -> None:
    """Both directions in one assertion, the liveness FS_EXEMPT_FILES stops short
    of: an entry is dead text -- the same failure as an exemption for a file that
    has moved -- if its file does not exist, OR if that file makes no module-level
    call by that name any more. A wholly bogus entry (a file that does not exist, a
    call never made) must fail here rather than pass 883 other tests green."""
    problems = []
    for rel_path, call_name in MODULE_LEVEL_CALL_EXEMPT:
        path = REPO_ROOT / rel_path
        if not path.is_file():
            problems.append(f"{rel_path}: no such file")
            continue
        made = _module_level_call_names(ast.parse(path.read_text(encoding="utf-8")))
        if call_name not in made:
            problems.append(f"{rel_path}: makes no module-level call named {call_name!r}")

    assert problems == [], problems


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


def test_the_export_walk_covers_every_first_party_package() -> None:
    """EXPORT_ROOTS decides which trees ``test_every_export_list_matches_its_module``
    reads, and that test was its only reader -- so narrowing the roster narrowed its
    own check, and cutting it to ``("sdg1531",)`` left every ``__all__`` under
    ``tests/`` and ``tools/`` compared against nothing while twelve tests passed.
    An ``app`` package would have landed into the same silence.

    Recomputed from the packages on disk instead, so it fails in both directions: a
    package that lands under a name nobody added is missing from the roster, and a
    root that is no longer a package is on it for nothing.
    """
    assert set(EXPORT_ROOTS) == _first_party_packages()


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
