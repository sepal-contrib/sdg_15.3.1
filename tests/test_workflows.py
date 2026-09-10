"""The CI workflows, read as artefacts rather than trusted as configuration.

A CI job is a proof, and a proof that agrees with itself proves nothing. The ways
a green job can mean nothing are all mechanical, so they are all checkable here,
on the PR gate, rather than discovered from a build that was passing all along:

* a ``-m`` selection that matches no test (it exits 5 today, but the count is what
  the claim rests on, and the nightly's selection would otherwise only be measured
  at 03:17 UTC);
* a job that COUNTS its tests and never runs them -- ``--collect-only`` proves a
  selection is not empty and executes nothing;
* a job or step switched off by an ``if:``, which reports as skipped, which branch
  protection treats as satisfied in its common configuration;
* a glob or path that matches nothing after a rename;
* a test run narrowed to one path, which overrides ``testpaths``;
* a lint or type command narrower than the one a developer runs locally;
* a step whose failure does not fail the job.

Everything below is derived from the workflow files themselves. The one name typed
by hand is ``ci``: the job that predates this task, whose *Verify ee-api fork*,
*Verify notebook kernelspec* and *Test UI notebook* steps guard the still-live
Voila entrypoint and are the companion spec's to retire (§15.7). It is named so
that the two rules it cannot satisfy -- its scripts predate ``set -e`` and its
kernelspec step deliberately runs outside the micromamba environment -- are
exclusions someone wrote down, rather than rules quietly weakened for everybody.
"""

from __future__ import annotations

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

    Anchored on the word ``pytest`` and cut at the next pipe, because ``-m`` is a
    flag on plenty of other commands: the `ci` job's ``python -m ipykernel`` was
    read as a marker expression by a regex that scanned whole lines. The same slice
    is what the rules below read, so "what the job passes pytest" is decided once.
    """
    return [
        (workflow, job, line[match.start() :].split("|")[0])
        for workflow, job, step in _run_steps()
        for line in _script_lines(step)
        for match in re.finditer(r"\bpytest\b", line)
    ]


def _marker_expressions() -> set[str]:
    """Every ``-m`` a ``pytest`` invocation in any workflow passes."""
    return {
        next(group for group in m.groups() if group is not None)
        for _, _, command in _pytest_commands()
        for m in _MARKER_FLAG.finditer(command)
    }


def _collected(marker: str) -> int:
    """How many tests ``pytest -m <marker>`` selects, from a clean subprocess."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            marker,
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
    assert proc.returncode in (0, 5), f"-m {marker!r} did not collect:\n{proc.stdout}{proc.stderr}"
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
    """The `ci` job guards the Voila entrypoint and is §15.7's to retire, not this
    task's. Its kernelspec step reads ui.ipynb, so deleting the notebook makes the
    workflow raise FileNotFoundError on the first port PR."""
    steps = _jobs(WORKFLOW_DIR / "ci.yaml")[LEGACY_JOB]["steps"]
    names = [step.get("name") for step in steps]

    for required in APP_LAYER_STEPS:
        assert required in names, f"{required!r} is gone from the {LEGACY_JOB} job: {names}"
    assert (REPO_ROOT / "ui.ipynb").is_file()


def test_every_job_that_counts_its_tests_also_runs_them() -> None:
    """``--collect-only`` proves a selection is not empty and executes nothing.

    Delete the ``pytest -m "not network" -q --durations=10`` line from the domain
    job and every other assertion in this file still holds: the marker expression
    survives in the collection guard above it, so the job counts the whole offline
    suite, prints ``selected <n> offline tests`` and exits 0 having run none of it.
    Counting is the claim to run, so it is what the rule is anchored on -- and a job
    that drops BOTH lines loses its marker expression, which
    :func:`test_every_marker_expression_selects_tests` compares as an exact set.
    """
    commands = _pytest_commands()
    counting = {(workflow, job) for workflow, job, c in commands if "--collect-only" in c}
    running = {(workflow, job) for workflow, job, c in commands if "--collect-only" not in c}

    idle = sorted(counting - running)
    assert idle == [], f"jobs that count their tests and never run them: {idle}"


def test_no_test_run_narrows_itself_to_a_path() -> None:
    """A path argument overrides ``testpaths``, so ``pytest -m "not network" -q
    tests/test_workflows.py`` is a green domain job that ran one file -- the same
    silent narrowing the lint job's bare invocations exist to prevent, one command
    over. The `ci` job is exempt because ``pytest --nbmake ui.ipynb`` names
    the notebook on purpose."""
    named = []
    for workflow, job, command in _pytest_commands():
        if job == LEGACY_JOB:
            continue
        named += [
            f"{workflow}:{job}: {token}"
            for token in shlex.split(command)[1:]
            if not token.startswith("-") and (REPO_ROOT / token).exists()
        ]

    assert named == [], f"a test run names a path, so its selection can narrow: {named}"


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
    empty = sorted(expr for expr in expressions if _collected(expr) == 0)
    assert empty == [], f"marker expressions that select no test: {empty}"
