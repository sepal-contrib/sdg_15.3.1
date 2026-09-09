"""Tier-0 guard 3 — importing the domain must touch nothing.

parameter/directory.py:7,10 calls mkdir at import today, and parameter/__init__.py
star-imports it, so importing any legacy science module creates ~/module_results.
The port forbids that outright (spec §4, §7).
"""

from __future__ import annotations

from pathlib import Path

from _subprocess import run_python

_SCRIPT = """
import builtins, importlib, os, pathlib, pkgutil, socket, sys

import ee  # imported before the patches: its own module-level reads are not the subject

HOME = os.path.abspath(os.environ["HOME"])


def _boom(*args, **kwargs):
    raise AssertionError("import-time side effect: %r %r" % (args, kwargs))


_real_open = builtins.open


def _open(file, mode="r", *args, **kwargs):
    path = "" if isinstance(file, int) else os.fspath(file)
    if isinstance(path, bytes):
        path = path.decode()
    if (set(mode) & set("wxa+")) or (path and os.path.abspath(path).startswith(HOME)):
        raise AssertionError("import-time file access: %r mode=%r" % (file, mode))
    return _real_open(file, mode, *args, **kwargs)


builtins.open = _open
os.mkdir = _boom
os.makedirs = _boom
pathlib.Path.mkdir = _boom
socket.socket = _boom
ee.Initialize = _boom

import sdg1531

names = [m.name for m in pkgutil.walk_packages(sdg1531.__path__, "sdg1531.")]
for name in names:
    importlib.import_module(name)
print("IMPORTED", len(names))
"""


def test_importing_the_domain_creates_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    proc = run_python(_SCRIPT, env={"HOME": str(home), "USERPROFILE": str(home)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "IMPORTED" in proc.stdout
    assert list(home.iterdir()) == [], f"import wrote into HOME: {list(home.iterdir())}"


def test_the_patches_actually_bite(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    guilty = _SCRIPT + '\npathlib.Path(os.environ["HOME"], "module_results").mkdir()\n'
    proc = run_python(guilty, env={"HOME": str(home), "USERPROFILE": str(home)})
    assert proc.returncode != 0
    assert "import-time side effect" in (proc.stdout + proc.stderr)
    assert list(home.iterdir()) == []
