"""The CI workflows, read as artefacts rather than trusted as configuration.

A CI job is a proof, and a proof that agrees with itself proves nothing. The ways
a green job can mean nothing are all mechanical, so they are all checkable here,
on the PR gate, rather than discovered from a build that was passing all along:

* a ``-m`` selection that matches no test (it exits 5 today, but the count is what
  the claim rests on, and the nightly's selection would otherwise only be measured
  at 03:17 UTC);
* a job that COUNTS its tests and never runs them -- ``--collect-only``, or the
  ``--co`` alias, proves a selection is not empty and executes nothing;
* a job or step switched off by an ``if:``, which reports as skipped, which branch
  protection treats as satisfied in its common configuration;
* a glob or path that matches nothing after a rename;
* a run narrowed under its own marker -- by ``-k``, ``--deselect``, ``--ignore`` or a
  path -- which is measured here rather than enumerated, because the flags that can
  do it are an open list and the count they produce is not;
* a lint or type command narrower than the one a developer runs locally;
* a step whose failure does not fail the job.

Everything below is derived from the workflow files themselves. The one name typed
by hand is ``ci``: the job that predates this task, whose *Verify ee-api fork*,
*Verify notebook kernelspec* and *Test UI notebook* steps guard the still-live
Voila entrypoint and are the app-layer migration's to retire. It is named so
that the two rules it cannot satisfy -- its scripts predate ``set -e`` and its
kernelspec step deliberately runs outside the micromamba environment -- are
exclusions someone wrote down, rather than rules quietly weakened for everybody.
"""

from __future__ import annotations

import functools
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import REPO_ROOT

WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.y*ml"))

LEGACY_JOB = "ci"
APP_LAYER_STEPS = ("Verify ee-api fork", "Verify notebook kernelspec", "Test UI notebook")

# `pytest -m <expr>`, in any of the three quotings a shell accepts.
_MARKER_FLAG = re.compile(r"""-m\s+(?:"([^"]+)"|'([^']+)'|([^\s|)]+))""")

# Ways a step's failure can stop failing its job. `set +e` cancels the guard the
# rule below requires; the rest swallow one command's exit code. `continue-on-error`
# is not here because it is not a shell spelling: it is a YAML key, read as one.
_SUPPRESSORS = ("|| true", "|| :", "|| exit 0", "; true", "set +e")

# What a test run may carry besides its marker: flags that change how the run is
# REPORTED, never which tests it selects. See `_runs_the_selection` for why this is
# an allowlist and not a list of the flags that narrow.
_REPORTING_FLAGS = ("-q", "--quiet", "--durations")


def _load(path: Path) -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document


def _triggers(document: dict[str, Any]) -> dict[str, Any]:
    """The workflow's ``on:`` block.

    YAML 1.1 resolves an unquoted ``on`` to the boolean ``True``, so ``d["on"]``
    raises KeyError on a file GitHub reads perfectly well.
    """
    for key in (True, "on"):
        if key in document:
            block: dict[str, Any] = document[key]
            return block
    raise AssertionError(f"no trigger block: {sorted(document)}")


def _jobs(path: Path) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = _load(path)["jobs"]
    return jobs


def _run_steps() -> list[tuple[str, str, dict[str, Any]]]:
    """``(workflow file name, job name, step)`` for every step that runs a script."""
    found = []
    for path in WORKFLOWS:
        for job_name, job in _jobs(path).items():
            for step in job["steps"]:
                if "run" in step:
                    found.append((path.name, job_name, step))
    return found


def _script_lines(step: dict[str, Any]) -> list[str]:
    """The script's lines, without blanks or comments."""
    return [
        line.strip()
        for line in step["run"].splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _pytest_commands() -> list[tuple[str, str, str]]:
    """``(workflow file name, job name, command)`` for every ``pytest`` invocation.

    Anchored on the word ``pytest``, because ``-m`` is a flag on plenty of other
    commands: the `ci` job's ``python -m ipykernel`` was read as a marker expression
    by a regex that scanned whole lines. Cut at the first shell metacharacter that
    ends a command, so what comes back is the invocation and nothing around it --
    cutting at ``|`` alone left the collection guard's ``> collected.txt`` in the
    token stream, where a repo file of that name would have been read as an argument.
    The same slice is what the rules below read, so "what the job passes pytest" is
    decided once.
    """
    return [
        (workflow, job, re.split(r"[|><;&]", line[match.start() :])[0])
        for workflow, job, step in _run_steps()
        for line in _script_lines(step)
        for match in re.finditer(r"\bpytest\b", line)
    ]


def _arguments(command: str) -> tuple[str, ...]:
    """The invocation's arguments, ``pytest`` itself dropped."""
    return tuple(shlex.split(command)[1:])


def _selection_arguments(arguments: tuple[str, ...]) -> tuple[str, ...]:
    """``arguments`` with the reporting flags dropped: what is left decides the
    selection, and only that is worth measuring.

    Dropping them rather than keeping them is not cosmetic. ``-q`` counts
    cumulatively, so an invocation that already carries one, measured by a collection
    that adds another, is a ``-qq`` run: pytest stops listing test ids and the count
    read off that output is zero for every invocation, equally and uninformatively.
    """
    return tuple(a for a in arguments if a.split("=")[0] not in _REPORTING_FLAGS)


def _marker_pair(arguments: tuple[str, ...]) -> tuple[str, ...]:
    """The ``-m <expr>`` pair out of an argument list, or ``()`` if there is none."""
    for index, argument in enumerate(arguments[:-1]):
        if argument == "-m":
            return (argument, arguments[index + 1])
    return ()


def _marker_expressions() -> set[str]:
    """Every ``-m`` a ``pytest`` invocation in any workflow passes."""
    return {
        next(group for group in m.groups() if group is not None)
        for _, _, command in _pytest_commands()
        for m in _MARKER_FLAG.finditer(command)
    }


def _runs_the_selection(command: str) -> bool:
    """Whether this invocation RUNS what its marker selects, or does something less.

    Decided from the WHOLE argument set, by allowlist: a run carries its marker
    expression and flags that change how it is REPORTED, and nothing else. The
    denylist is the open-ended one -- ``-k``, ``--deselect``, ``--ignore``,
    ``--last-failed``, a bare path, and ``--collect-only`` under every spelling
    argparse accepts for it (``--co`` is the alias that got past a check for the
    literal) are one flag each, and a rule that enumerates them is a rule that is one
    pytest release from being wrong again. Anything not on the allowlist means this
    invocation does not count as the job's run, so adding a flag to a CI test command
    is a decision recorded here.
    """
    arguments = list(_arguments(command))
    while arguments:
        argument = arguments.pop(0)
        if argument == "-m":  # the marker expression, measured by the rules below
            if arguments:
                arguments.pop(0)
            continue
        if argument.split("=")[0] not in _REPORTING_FLAGS:
            return False
    return True


@functools.cache
def _collected(arguments: tuple[str, ...]) -> int:
    """How many tests ``pytest <arguments>`` selects, from a clean subprocess."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *arguments,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # 0 = tests collected, 5 = none collected; anything else is a collection error
    assert proc.returncode in (0, 5), f"{arguments} did not collect:\n{proc.stdout}{proc.stderr}"
    return sum(1 for line in proc.stdout.splitlines() if "::" in line)


def test_the_workflow_glob_found_the_workflows() -> None:
    """Every test below iterates this glob, so an empty one passes them all."""
    names = {path.name for path in WORKFLOWS}

    assert {"ci.yaml", "nightly.yaml"} <= names, names


def test_ci_yaml_declares_the_pr_gate_jobs() -> None:
    assert sorted(_jobs(WORKFLOW_DIR / "ci.yaml")) == ["ci", "domain", "lint"]


def test_the_nightly_workflow_is_scheduled_and_dispatchable() -> None:
    document = _load(WORKFLOW_DIR / "nightly.yaml")
    triggers = _triggers(document)

    assert sorted(document["jobs"]) == ["network"]
    assert triggers["schedule"] == [{"cron": "17 3 * * *"}]
    # without this a broken nightly cannot be re-run until tomorrow
    assert "workflow_dispatch" in triggers


def test_the_app_layer_checks_are_intact() -> None:
    """The `ci` job guards the Voila entrypoint and is the app-layer migration's to
    retire, not this port's. Its kernelspec step reads ui.ipynb, so deleting the
    notebook makes the workflow raise FileNotFoundError on the first port PR."""
    steps = _jobs(WORKFLOW_DIR / "ci.yaml")[LEGACY_JOB]["steps"]
    names = [step.get("name") for step in steps]

    for required in APP_LAYER_STEPS:
        assert required in names, f"{required!r} is gone from the {LEGACY_JOB} job: {names}"
    assert (REPO_ROOT / "ui.ipynb").is_file()


def test_every_pytest_job_actually_executes_its_selection() -> None:
    """A job may collect, filter and report as much as it likes, as long as ONE of
    its invocations is a plain run: the marker expression, reporting flags, nothing
    else.

    Every way a job can appear to run tests without running them lands here, and it
    does not matter which one anybody thought of. Deleting the domain job's
    ``pytest -m "not network" -q --durations=10`` leaves only the collection guard,
    which is not a run. Spelling that line ``--co`` -- pytest's own alias, which a
    check for the literal ``--collect-only`` reads as a run -- leaves the job
    collecting twice and executing nothing. Adding ``-k`` or ``--deselect`` to it
    leaves it running a fraction while the guard above still prints the whole count.
    None of those is enumerated: they are all simply not a plain run.

    A job that drops its pytest lines ENTIRELY is out of this rule's scope and in
    :func:`test_every_marker_expression_selects_tests`'s, which compares the marker
    expressions across both workflows as an exact set.
    """
    invoking = {(workflow, job) for workflow, job, _ in _pytest_commands() if job != LEGACY_JOB}
    running = {
        (workflow, job)
        for workflow, job, command in _pytest_commands()
        if job != LEGACY_JOB and _runs_the_selection(command)
    }

    idle = sorted(invoking - running)
    assert idle == [], (
        f"jobs that invoke pytest and never plainly run it: {idle}. A run carries its "
        f"marker and {list(_REPORTING_FLAGS)} and nothing else."
    )


@pytest.mark.slow
def test_no_pytest_invocation_narrows_what_its_marker_selects() -> None:
    """The selection each invocation would really make, MEASURED against the one its
    marker alone makes.

    ``-k "test_domain_package_imports"`` on the domain job's run line is ONE test
    with the marker untouched, no path named, and the collection guard above it
    still printing the whole count. ``--deselect`` drops a test; ``--ignore`` drops
    a tree, and ``--ignore=tests/parity`` takes the entire Tier-4 harness with it;
    a bare path overrides ``testpaths``. Rather than enumerate those, each
    invocation is COLLECTED as written and compared against its own marker pair, so
    a flag nobody here thought of narrows the count just the same and fails just the
    same.

    The `ci` job is exempt: ``pytest --nbmake ui.ipynb`` names the notebook on
    purpose, and it is the app-layer migration's to retire.
    """
    problems = []
    for workflow, job, command in _pytest_commands():
        if job == LEGACY_JOB:
            continue
        arguments = _selection_arguments(_arguments(command))
        selected = _collected(arguments)
        whole = _collected(_marker_pair(arguments))
        if selected != whole:
            problems.append(f"{workflow}:{job}: `{command.strip()}` selects {selected} of {whole}")

    assert problems == [], problems


def test_no_job_or_step_is_switched_off_by_a_condition() -> None:
    """A job that never runs reports as SKIPPED, and branch protection treats a
    skipped required check as satisfied in its common configuration -- so ``if:
    false`` on the domain job is a merge gate that gates nothing, with every other
    assertion here green. A step-level ``if:`` empties a job just as thoroughly.

    Absence, rather than a judgement about which expressions are constantly false:
    no job in either workflow has a condition today, the `ci` job included, so
    there is nothing to weigh and the day one is wanted it is a decision someone
    writes down here.
    """
    offenders = []
    for path in WORKFLOWS:
        for job_name, job in _jobs(path).items():
            if "if" in job:
                offenders.append(f"{path.name}:{job_name}: if: {job['if']}")
            offenders += [
                f"{path.name}:{job_name}:{step.get('name')}: if: {step['if']}"
                for step in job["steps"]
                if "if" in step
            ]

    assert offenders == [], f"jobs or steps a condition can switch off: {offenders}"


def test_no_step_can_fail_without_failing_its_job() -> None:
    """``continue-on-error`` is read as the parsed key it is, at both the job and
    the step level, and the shell spellings are looked for in the script rather
    than in the file: a comment explaining why a step does NOT use ``|| true`` is
    not a step that uses it, and the whole-file text scan this replaced would have
    failed the job for saying so."""
    offenders = []
    for path in WORKFLOWS:
        for job_name, job in _jobs(path).items():
            if job.get("continue-on-error"):
                offenders.append(f"{path.name}:{job_name}: continue-on-error")
            for step in job["steps"]:
                where = f"{path.name}:{job_name}:{step.get('name')}"
                if step.get("continue-on-error"):
                    offenders.append(f"{where}: continue-on-error")
                if "run" not in step:
                    continue
                for line in _script_lines(step):
                    offenders += [f"{where}: {s}" for s in _SUPPRESSORS if s in line]

    assert offenders == [], offenders


def test_every_multi_command_script_stops_at_the_first_failure() -> None:
    """A multi-line ``run:`` reports only its LAST command's exit code unless the
    shell is told otherwise, and whether it is told depends on the custom shell the
    setup action registers. A job that ends in an ``echo`` would go green over a
    failed pytest above it."""
    offenders = []
    for workflow, job, step in _run_steps():
        if job == LEGACY_JOB:
            continue
        lines = _script_lines(step)
        if len(lines) > 1 and not re.match(r"^set -[a-z]*e", lines[0]):
            offenders.append(f"{workflow}:{job}:{step.get('name')} starts with {lines[0]!r}")

    assert offenders == [], offenders


def test_every_new_step_runs_inside_the_micromamba_environment() -> None:
    """A step that forgets ``shell: micromamba-shell {0}`` runs against the runner's
    own python, where the package is not installed and the pins do not apply."""
    offenders = [
        f"{workflow}:{job}:{step.get('name')}"
        for workflow, job, step in _run_steps()
        if job != LEGACY_JOB and step.get("shell") != "micromamba-shell {0}"
    ]

    assert offenders == [], offenders


def test_the_lint_job_names_no_paths() -> None:
    """Naming paths is how a lint job silently narrows. ``mypy sdg1531`` reads 28
    files where ``[tool.mypy] files`` reads 42, and ``ruff check sdg1531 tests
    tools`` stops covering the app package the day it lands. A bare invocation
    reads the same configuration the local run reads, so the two cannot drift."""
    named = []
    for _, job, step in _run_steps():
        if job != "lint":
            continue
        for line in _script_lines(step):
            tokens = shlex.split(line)
            if tokens[0] not in ("ruff", "mypy"):
                continue
            named += [t for t in tokens[1:] if (REPO_ROOT / t).exists()]

    assert named == [], f"the lint job names paths, so its file set can narrow: {named}"


def test_the_lint_job_runs_every_local_gate() -> None:
    scripts = " ".join(
        line for _, job, step in _run_steps() if job == "lint" for line in _script_lines(step)
    )

    for command in ("ruff check", "ruff format --check", "mypy"):
        assert command in scripts, f"the lint job never runs {command!r}: {scripts}"


def test_no_job_runs_stage_a() -> None:
    """``tools/dump_legacy_graphs.py`` imports the legacy tree, and
    ``component/parameter/directory.py:6-10`` mkdirs ``~/module_results`` at import.
    Stage A is a local, deliberate act; a job that runs it writes into the runner's
    home directory and must say so."""
    offenders = [
        f"{workflow}:{job}:{step.get('name')}"
        for workflow, job, step in _run_steps()
        if "dump_legacy_graphs" in step["run"]
    ]

    assert offenders == [], offenders


@pytest.mark.slow
def test_every_marker_expression_selects_tests() -> None:
    """The selection is measured, not inferred from an exit code.

    ``pytest -m network`` over an empty selection exits 5, which does fail a job --
    but only the nightly ever evaluates the nightly's expression, so a marker
    dropped in a refactor would sit undetected until it ran. This measures both
    expressions on every PR.
    """
    expressions = _marker_expressions()

    assert expressions == {"not network", "network"}, expressions
    empty = sorted(expr for expr in expressions if _collected(("-m", expr)) == 0)
    assert empty == [], f"marker expressions that select no test: {empty}"
