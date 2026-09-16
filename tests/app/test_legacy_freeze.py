"""The legacy science is frozen: the parity harness imports it.

Stage A of the parity harness runs `component/scripts/run_15_3_1.py` against
`component/model/indicator_model.py` to produce the golden graphs the port is
compared to. An innocent edit there silently invalidates the D9 evidence, so
this pins the four directories that must not move.
"""

from __future__ import annotations

import pathlib
import subprocess

FROZEN = ("component/model", "component/scripts", "component/parameter", "component/message")
FREEZE_COMMIT = "bb72d2510ee897764cff3293603dea5f4273e360"


def test_the_frozen_legacy_is_unmodified():
    changed = subprocess.run(
        ["git", "diff", "--name-only", FREEZE_COMMIT, "--", *FROZEN],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert changed == [], f"the parity reference was modified: {changed}"


def test_the_reclassify_files_survive():
    """Spec 2 owns these; spec 1 must not take them with the rest of the UI."""
    assert pathlib.Path("component/widget/reclassify").is_dir()
    assert pathlib.Path("component/tile/reclassify_tile.py").is_file()


def test_the_notebook_survives():
    """CI's kernelspec step reads it; spec 3 replaces that workflow."""
    assert pathlib.Path("ui.ipynb").is_file()
