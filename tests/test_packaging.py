"""pyproject must actually install, and must carry the config the suite assumes exists."""

from __future__ import annotations

import tomllib
from fnmatch import fnmatch

from conftest import REPO_ROOT


def _pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_domain_package_imports() -> None:
    import sdg1531

    assert isinstance(sdg1531.__all__, tuple)


def test_build_system_is_declared() -> None:
    build = _pyproject()["build-system"]
    assert "setuptools" in " ".join(build["requires"])
    assert build["build-backend"] == "setuptools.build_meta"


def test_requires_python_is_312() -> None:
    assert _pyproject()["project"]["requires-python"] == ">=3.12"


def test_runtime_dependencies_are_declared() -> None:
    deps = _pyproject()["project"]["dependencies"]
    names = {d.split("[")[0].split(">")[0].split("=")[0].split("<")[0].strip() for d in deps}
    # the domain is ee + pandas + geopandas + stdlib and nothing else, plus
    # anyascii: pure-Python, zero dependencies, required so
    # sdg1531.naming.normalize_str transliterates non-Latin AOI names
    # byte-identically to the legacy pysepal scripts/utils.py:140.
    assert names == {"earthengine-api", "pandas", "geopandas", "anyascii"}


def test_dev_and_app_extras_exist() -> None:
    extras = _pyproject()["project"]["optional-dependencies"]
    dev = " ".join(extras["dev"])
    for tool in ("pytest", "pytest-asyncio", "hypothesis", "ruff", "mypy", "pyyaml"):
        assert tool in dev, tool
    app = " ".join(extras["app"])
    # pysepal is installed from the editable checkout, not pinned here, so this
    # only names the runtime deps pyproject itself must declare.
    for tool in ("solara", "ipecharts"):
        assert tool in app, tool


def test_only_the_domain_and_app_packages_are_discovered() -> None:
    find = _pyproject()["tool"]["setuptools"]["packages"]["find"]
    assert find["include"] == ["sdg1531*", "app*"]
    # the legacy tree must never be shipped
    assert "component" not in " ".join(find.get("include", []))


def test_pytest_markers_are_registered() -> None:
    markers = _pyproject()["tool"]["pytest"]["ini_options"]["markers"]
    prefixes = {m.split(":")[0] for m in markers}
    assert {"network", "parity", "slow"} <= prefixes


def test_ruff_and_mypy_target_the_domain_by_name() -> None:
    cfg = _pyproject()["tool"]
    assert cfg["ruff"]["target-version"] == "py312"
    assert "component" in cfg["ruff"]["extend-exclude"]
    assert cfg["mypy"]["strict"] is True
    assert "sdg1531" in cfg["mypy"]["files"]


def test_ruff_excludes_no_first_party_tree() -> None:
    """The lint job passes ruff no paths, deliberately (`.github/workflows/ci.yaml`),
    so its file set is decided entirely by the config a local run also reads. That
    moves the narrowing risk here: appending `"sdg1531", "tests", "tools"` to
    `extend-exclude` takes `ruff format --check` from 86 files to 2 with every test
    that polices this configuration still green. It is the same hole an `exclude`
    pattern would open in mypy, which the test below closes on that side. `app` is
    on the list before it exists, the way `hygiene_rules.ROOTS` carries it.
    """
    excluded = _pyproject()["tool"]["ruff"]["extend-exclude"]
    trees = ("sdg1531", "tests", "tools", "app")

    narrowed = [
        pattern
        for pattern in excluded
        for tree in trees
        if pattern == tree or pattern.startswith(f"{tree}/") or fnmatch(tree, pattern)
    ]
    assert narrowed == [], f"ruff patterns that exclude a first-party tree: {narrowed}"


def test_mypy_reads_the_parity_harness_and_its_tools() -> None:
    """`files` was `["sdg1531"]`, so the two files the parity guarantee rests on --
    `tests/parity/canonical.py`, which decides whether two ee graphs match, and
    `tools/to_legacy_model.py`, the sole adapter every golden was recorded through
    -- read as type-checked while mypy never opened them. Widening it found a real
    defect in the adapter on the first run.

    Checking `files` alone would leave this test's name broader than its body: an
    `exclude` regex, or an override switching `ignore_errors` on, takes those trees
    back out of the check while `files` still names them. Reading means all three.
    """
    mypy = _pyproject()["tool"]["mypy"]
    trees = ("sdg1531", "tools", "tests/parity")

    assert set(trees) <= set(mypy["files"])
    assert "exclude" not in mypy, f"an exclude pattern can take {trees} back out: {mypy}"

    silenced = [
        override["module"]
        for override in mypy.get("overrides", [])
        if override.get("ignore_errors") or override.get("follow_imports") in ("skip", "silent")
        if any(str(m).split(".")[0] in ("sdg1531", "tools", "tests") for m in override["module"])
    ]
    assert silenced == [], f"overrides silencing a checked tree: {silenced}"
