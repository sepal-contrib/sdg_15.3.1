"""Run a snippet in a clean interpreter rooted at the repo.

``python -c`` puts the working directory on ``sys.path[0]``, which is what makes
``import sdg1531`` resolve to the checkout without an install step.
"""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import REPO_ROOT

__all__ = ["REPO_ROOT", "run_python"]


def run_python(code: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    child_env = dict(os.environ)
    if env:
        child_env.update(env)
    child_env.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=300,
    )
