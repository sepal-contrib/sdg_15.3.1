"""Validation routing: every problem reaches exactly one step."""

from __future__ import annotations

from app.state import STEP_PREFIXES, is_runnable, problems_for
from sdg1531.spec import RunSpec
from sdg1531.validate import validate
from tests.spec_factory import default_spec


def _all_emitted_fields() -> set[str]:
    """Every `field` value validate() can emit, harvested from the source
    rather than guessed -- a hand-written list would go stale silently."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("sdg1531/validate.py").read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.keyword)
            and node.arg == "field"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found.add(node.value.value)
    return found


def test_every_problem_field_is_owned_by_exactly_one_step():
    """A new Problem must not be introduced with nowhere to display it, and
    two steps must not both claim the same field -- the user would see the
    error twice."""
    owners = {
        field: [
            step
            for step, prefixes in STEP_PREFIXES.items()
            if any(field == p or field.startswith(p + ".") for p in prefixes)
        ]
        for field in _all_emitted_fields()
        if field  # the whole-spec field "" is the Run step's, handled below
    }
    unowned = sorted(f for f, o in owners.items() if not o)
    shared = sorted(f for f, o in owners.items() if len(o) > 1)
    assert unowned == [], f"no step displays: {unowned}"
    assert shared == [], f"claimed by more than one step: {shared}"


def test_the_whole_spec_field_belongs_to_the_run_step():
    """validate() emits field="" for problems about the run as a whole."""
    assert "" in STEP_PREFIXES["run"]


def test_problems_for_filters_to_the_step():
    spec = RunSpec()  # unfilled: aoi and vi_source are both unset
    aoi_problems = problems_for("aoi", spec)
    assert aoi_problems
    assert all(p.field.startswith("aoi") for p in aoi_problems)


def test_an_unfilled_spec_is_not_runnable():
    assert is_runnable(RunSpec()) is False


def test_a_complete_spec_is_runnable():
    assert is_runnable(default_spec()) is True


def test_validate_never_raises_on_a_half_filled_spec():
    """problems_for runs on every render while the user is still typing, so a
    raise here would take the whole step down."""
    for spec in (RunSpec(), default_spec()):
        assert isinstance(validate(spec), tuple)
