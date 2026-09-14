"""Validation routing: every problem reaches exactly one step.

The AST harvest below (`_all_emitted_fields`) is the coverage guard's source of
truth for which fields `validate()` can emit -- not a hand-written list, which
would go stale silently, and not a runtime sweep over sample specs, which
under-approximates: it only reports what some spec in the sample happened to
trigger, so a new rule nobody wrote a spec for stays invisible. Two things keep
the harvest itself honest: a sentinel floor (`test_every_problem_field_is_owned...`
refuses to run its ownership check if the harvest is suspiciously small) and a
loud failure on anything the harvester cannot resolve, rather than silently
dropping it (`test_harvester_refuses_*`).
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import fields as dataclass_fields
from dataclasses import replace

import pytest

import sdg1531.validate
from app.state import STEP_PREFIXES, _owns, is_runnable, problems_for
from sdg1531.catalog import DISABLED_TRAJECTORIES
from sdg1531.scheme import TransitionMatrix
from sdg1531.spec import FixedClimate, Period, PeriodOverride, RunSpec, SubPeriods
from sdg1531.validate import validate
from tests.spec_factory import DEFAULT_PERIODS, default_spec

# --------------------------------------------------------------- the AST harvest


def _param_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = fn.args
    return [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]


def _enclosing_functions(tree: ast.AST) -> dict[ast.AST, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Map every node to its innermost enclosing function, if any."""
    enclosing: dict[ast.AST, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    stack: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    def visit(node: ast.AST) -> None:
        if stack:
            enclosing[node] = stack[-1]
        is_func = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if is_func:
            stack.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)
        if is_func:
            stack.pop()

    visit(tree)
    return enclosing


def _literal_at(call: ast.Call, index: int, name: str) -> str | None:
    """The string literal `call` passes at positional `index` or keyword `name`."""
    if index < len(call.args) and isinstance(call.args[index], ast.Constant):
        value = call.args[index].value
        if isinstance(value, str):
            return value
    for kw in call.keywords:
        if (
            kw.arg == name
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return kw.value.value
    return None


def _harvest_problem_fields(source: str) -> frozenset[str]:
    """Every string `Problem(field=...)` value `source` can produce.

    Most call sites pass a literal directly. A few (`_matrix_problems`,
    `_codes_problem`) take `field` as their own parameter and forward it, so the
    literal lives one hop away at their call sites instead. This follows exactly
    that one hop: for `Problem(field=x)` where `x` is a parameter of the
    enclosing function, it finds every call to that function and harvests the
    literal passed at `x`'s position or keyword.

    Anything it cannot resolve that way -- a second hop of forwarding, an
    f-string, a module-level constant, a call with no matching literal -- raises
    `AssertionError` naming the line, rather than silently shrinking the
    harvest. Silence is the failure mode this exists to prevent: a resolver that
    swallows what it cannot follow is exactly as blind as the plain-literal
    harvester it replaces.

    That guarantee covers only a call whose callee is the bare name `Problem`.
    An aliased name (`_P = Problem; _P(field=...)`) or an attribute-qualified
    call (`mod.Problem(field=...)`) is skipped silently, not raised --
    `validate.py` imports `Problem` directly and never aliases it, so neither
    shape appears in the file this harvester actually reads.

    Over-approximation is fine and expected: `check_custom_lc_codes` (whose
    `Problem`s `validate()` never actually emits, since nothing calls it) still
    contributes its two fields. A "must be owned" guard is safe to be too
    generous; it must never be too stingy.
    """
    tree = ast.parse(source)
    enclosing = _enclosing_functions(tree)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    fields: set[str] = set()

    def calls_to(name: str) -> list[ast.Call]:
        return [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == name]

    for node in calls:
        if not (isinstance(node.func, ast.Name) and node.func.id == "Problem"):
            continue
        field_kw = next((k for k in node.keywords if k.arg == "field"), None)
        if field_kw is None:
            raise AssertionError(f"line {node.lineno}: Problem(...) has no field= keyword")
        if isinstance(field_kw.value, ast.Constant) and isinstance(field_kw.value.value, str):
            fields.add(field_kw.value.value)
            continue
        if isinstance(field_kw.value, ast.Name):
            fn = enclosing.get(node)
            names = _param_names(fn) if fn is not None else []
            if fn is not None and field_kw.value.id in names:
                index = names.index(field_kw.value.id)
                sites = calls_to(fn.name)
                if sites:
                    for call in sites:
                        literal = _literal_at(call, index, field_kw.value.id)
                        if literal is None:
                            raise AssertionError(
                                f"line {call.lineno}: call to {fn.name}() does not pass a "
                                f"string literal at parameter {index} ({field_kw.value.id!r})"
                            )
                        fields.add(literal)
                    continue
        raise AssertionError(
            f"line {node.lineno}: field= is neither a string literal nor a one-hop "
            "parameter forward this harvester can resolve"
        )

    return frozenset(fields)


def _all_emitted_fields() -> frozenset[str]:
    """Every `field` value validate() can emit, harvested from the source rather
    than guessed -- a hand-written list would go stale silently."""
    source = pathlib.Path(sdg1531.validate.__file__).read_text()
    return _harvest_problem_fields(source)


# ----------------------------------------------------- harvester self-defense
#
# The harvest above must fail loudly on any shape it cannot follow, or the
# coverage guard it feeds can pass while checking nothing. These probe that
# arm directly, against synthetic source held in memory -- sdg1531/ is never
# touched.


def test_harvester_refuses_a_second_hop_of_indirection():
    src = (
        "def _outer(spec):\n"
        "    return _inner(spec.value)\n"
        "\n"
        "def _inner(field):\n"
        "    return Problem(field=field, code='c', message='m', fatal=True)\n"
    )
    with pytest.raises(AssertionError, match=r"line \d+"):
        _harvest_problem_fields(src)


def test_harvester_refuses_an_fstring_field():
    src = (
        "def _f(key):\n"
        '    return Problem(field=f"periods.{key}", code="c", message="m", fatal=True)\n'
    )
    with pytest.raises(AssertionError, match=r"line \d+"):
        _harvest_problem_fields(src)


def test_harvester_refuses_a_module_level_constant_field():
    src = (
        '_F = "sneaky"\n'
        "\n"
        "def _f():\n"
        "    return Problem(field=_F, code='c', message='m', fatal=True)\n"
    )
    with pytest.raises(AssertionError, match=r"line \d+"):
        _harvest_problem_fields(src)


def test_the_harvester_resolves_the_indirected_matrix_fields():
    """`_matrix_problems` forwards `field` through its own parameter, so a
    harvester that only reads literal keywords misses these two entirely."""
    assert {"transition_matrix", "land_cover.scheme.matrix"} <= _all_emitted_fields()


# ------------------------------------------------------- the routing table itself


def test_every_problem_field_is_owned_by_exactly_one_step():
    """A new Problem must not be introduced with nowhere to display it, and
    two steps must not both claim the same field -- the user would see the
    error twice."""
    fields = _all_emitted_fields()

    # A floor, not a ceiling: these four are deliberately chosen, one per
    # acquisition path (a plain literal, the whole-spec "", and the one-hop
    # resolution this harvester exists for) so that if the harvest ever comes
    # back empty or badly truncated, the guard below cannot pass vacuously.
    sentinel = {"", "aoi", "water_mask", "transition_matrix"}
    missing_sentinel = sorted(sentinel - fields)
    assert not missing_sentinel, (
        f"the harvester did not find {missing_sentinel} -- it has gone blind, not the routing table"
    )

    # No `if field` filter: "" (the whole-spec field) must clear this ownership
    # check exactly like any other field. Excluding it would leave a second step
    # free to claim "" alongside Run with nothing here to notice.
    owners = {
        field: [
            step
            for step, prefixes in STEP_PREFIXES.items()
            if any(_owns(p, field) for p in prefixes)
        ]
        for field in fields
    }
    unowned = sorted(f for f, o in owners.items() if not o)
    shared = sorted(f for f, o in owners.items() if len(o) > 1)
    assert unowned == [], f"no step displays: {unowned}"
    assert shared == [], f"claimed by more than one step: {shared}"


def test_runtime_validate_never_emits_a_field_the_ast_harvest_missed():
    """A cheap cross-check floor, not a source of truth: a hand-built corpus
    under-approximates (it only proves what these specific specs happen to
    trigger), but if `validate()` ever emits a field this AST harvest didn't
    find, the harvest itself has a bug worth knowing about immediately.
    """
    corpus = (
        RunSpec(),
        default_spec(periods=replace(DEFAULT_PERIODS, overall=Period(2020, 2000))),
        default_spec(water_mask=None),
        default_spec(trajectory=next(iter(DISABLED_TRAJECTORIES))),
        default_spec(climate=FixedClimate(coefficient=float("nan"))),
        default_spec(transition_matrix=TransitionMatrix(rows=((1,),))),
    )
    observed = {p.field for spec in corpus for p in validate(spec)}
    assert observed, "the runtime corpus provoked no problems at all -- it has gone stale"
    missing = sorted(observed - _all_emitted_fields())
    assert missing == [], f"validate() emitted fields the AST harvest missed: {missing}"


def test_the_whole_spec_field_belongs_to_the_run_step():
    """validate() emits field="" for problems about the run as a whole."""
    assert "" in STEP_PREFIXES["run"]


def test_every_prefix_head_names_a_real_spec_field():
    """The reverse direction: a prefix whose head matches no RunSpec/SubPeriods
    field points at nothing. Six prefixes are legitimately unexercised today
    (forward-looking claims for widgets not built yet), so this checks that
    every prefix names something real, not that every prefix currently fires.
    """
    run_spec_fields = {f.name for f in dataclass_fields(RunSpec)}
    sub_periods_fields = {f.name for f in dataclass_fields(SubPeriods)}
    for step, prefixes in STEP_PREFIXES.items():
        for prefix in prefixes:
            if not prefix:
                continue
            head, _, rest = prefix.partition(".")
            if head == "periods" and rest:
                sub_head = rest.split(".", 1)[0]
                assert sub_head in sub_periods_fields, (
                    f"{step}: {prefix!r} names no SubPeriods field"
                )
            else:
                assert head in run_spec_fields, f"{step}: {prefix!r} names no RunSpec field"


# ------------------------------------------------------------------ problems_for


def test_problems_for_partitions_by_the_routing_table_not_by_step_name():
    """Regression: every field below differs from the name of the step that owns
    it (aoi is the one unavoidable exception), so a `problems_for` that filtered
    by `field.startswith(step)` instead of consulting `STEP_PREFIXES` could not
    pass this the way it could pass a same-named probe like `problems_for("aoi", ...)`.
    """
    periods = replace(
        DEFAULT_PERIODS,
        overall=Period(2020, 2000),  # inverted -> run
        state=PeriodOverride(2010, 2020),  # explicit, does not fall back to overall
        land_cover=PeriodOverride(2005, 2015),  # explicit, does not fall back
        soc=PeriodOverride(1980, None),  # -> soc
    )
    spec = default_spec(
        periods=periods,
        aoi=None,  # -> aoi
        trajectory=next(iter(DISABLED_TRAJECTORIES)),  # -> productivity
        water_mask=None,  # -> land_cover
    )
    partition = {step: [p.field for p in problems_for(step, spec)] for step in STEP_PREFIXES}
    assert partition == {
        "aoi": ["aoi"],
        "productivity": ["trajectory"],
        "land_cover": ["water_mask"],
        "soc": ["periods.soc.start"],
        "run": ["periods.overall.start"],
    }


def test_problems_for_raises_on_an_unknown_step():
    """`STEP_PREFIXES` is the closed set of steps the app defines; a name outside
    it is a caller bug, not a half-filled form, and must not be swallowed into a
    silently empty result."""
    with pytest.raises(KeyError):
        problems_for("not_a_real_step", RunSpec())


def test_problems_for_never_raises_for_any_step_on_a_half_filled_spec():
    """problems_for runs on every render while the user is still typing, so a
    raise here would take the whole step down."""
    for spec in (RunSpec(), default_spec()):
        for step in STEP_PREFIXES:
            assert isinstance(problems_for(step, spec), tuple)


# -------------------------------------------------------------------- is_runnable


def test_an_unfilled_spec_is_not_runnable():
    assert is_runnable(RunSpec()) is False


def test_a_complete_spec_is_runnable():
    assert is_runnable(default_spec()) is True


def test_a_spec_with_only_a_warning_is_runnable():
    """Warnings must not block a run. `state_period_too_short` is one of four
    rules `sdg1531/validate.py`'s module docstring commits to non-fatal
    specifically so the Process button stays enabled -- an `is_runnable` that
    went warning-sensitive would silently undo that port decision.
    """
    spec = default_spec(periods=replace(DEFAULT_PERIODS, state=PeriodOverride(2018, 2020)))
    problems = validate(spec)
    assert problems and not any(p.fatal for p in problems)
    assert is_runnable(spec) is True
