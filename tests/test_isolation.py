"""Tier-0 guards 1 and 2 — the sys.meta_path blocker, and the ee-blocked JSON half.

Both passes run in a subprocess: pytest itself has already imported half of the
banned list, so an in-process blocker would be defeated by sys.modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _subprocess import run_python
from conftest import REPO_ROOT

BANNED_UI = (
    "solara",
    "ipyvuetify",
    "ipywidgets",
    "ipyleaflet",
    "ipecharts",
    "matplotlib",
    "traitlets",
    "sepal_ui",
    "pysepal",
    "component",
)

# spec §4: these may not import ee either. They are the JSON half, and that is
# what makes the parameter layer test in milliseconds.
JSON_HALF = (
    "sdg1531.errors",
    "sdg1531.enums",
    "sdg1531.catalog",
    "sdg1531.tables",
    "sdg1531.palette",
    "sdg1531.scheme",
    "sdg1531.spec",
    "sdg1531.validate",
    "sdg1531.resolve",
    "sdg1531.naming",
    "sdg1531.truth_table",
    "sdg1531.stats.plots",
)

_SCRIPT = '''
import importlib, importlib.util, pkgutil, sys

BANNED = {banned!r}
TARGETS = {targets!r}


class _Blocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BANNED:
            raise ImportError("tier-0 isolation guard blocked " + fullname)
        return None


sys.meta_path.insert(0, _Blocker())

# prove the guard is live, whether or not the banned package is installed
for name in BANNED:
    try:
        importlib.util.find_spec(name)
    except ImportError:
        continue
    print("GUARD-INERT:", name)
    raise SystemExit(2)

import sdg1531

targets = list(TARGETS)
if not targets:
    targets = [m.name for m in pkgutil.walk_packages(sdg1531.__path__, "sdg1531.")]
for name in targets:
    importlib.import_module(name)
print("IMPORTED", len(targets))
'''


def test_domain_imports_without_any_ui_library() -> None:
    proc = run_python(_SCRIPT.format(banned=BANNED_UI, targets=()))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "IMPORTED" in proc.stdout


def _module_exists(dotted: str) -> bool:
    """True once ``dotted`` has a source file on disk — no import, so this stays outside
    the subprocess boundary the rest of the file relies on for isolation.
    """
    base = REPO_ROOT / Path(*dotted.split("."))
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


# JSON_HALF is the roster later tasks fill in one module at a time; a name that does not
# exist yet is skipped, visibly, rather than silently dropped, so the suite tightens on
# its own as each module lands instead of needing every later task to remember it.
@pytest.mark.parametrize(
    "name",
    [
        pytest.param(name, marks=pytest.mark.skipif(not _module_exists(name), reason=f"{name} does not exist yet"))
        for name in JSON_HALF
    ],
)
def test_json_half_imports_without_ee(name: str) -> None:
    proc = run_python(_SCRIPT.format(banned=BANNED_UI + ("ee",), targets=(name,)))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_blocker_is_not_a_no_op() -> None:
    # a module that does import a banned library must fail the guard
    proc = run_python(_SCRIPT.format(banned=("json",), targets=()) + "\nimport json\n")
    assert proc.returncode != 0
    assert "tier-0 isolation guard blocked json" in (proc.stdout + proc.stderr)
