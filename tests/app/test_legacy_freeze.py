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
# The last domain-layer commit on this branch, one before app-layer work starts
# (`1697207`, "feat(app): scaffold the application package and its catalogue")
# -- the actual point the D9 freeze took effect, not merely a commit late enough
# to have seen no changes since. Re-anchored from `bb72d251`, which only proved
# the freeze held for the branch's last 33 commits; verified before moving it
# that neither anchor changes what the guard already proves: `git diff
# --name-only 1121498 -- component/{model,scripts,parameter,message}` and
# `git log 1121498..HEAD -- <those>` are both empty.
FREEZE_COMMIT = "1121498bfcd2b30f33d630f7a1982117fb34b086"


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
