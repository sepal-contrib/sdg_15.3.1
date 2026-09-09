"""The offline `ee` bootstrap that Tiers 3 and 4 sit on (spec §12).

Two behaviours of earthengine-api 1.6.14 are load-bearing and are asserted here
so that, when a release moves them, this file fails rather than the domain:

1. `ee.Initialize` accepts a duck-typed credential object.
2. The algorithm table decides what `ee.Image` can do; an empty table breaks it.
"""

import subprocess
import sys
import textwrap

import ee

from tests.ee_offline import load_ee_algorithms


def test_fixture_carries_the_pinned_ee_version():
    payload = load_ee_algorithms()
    assert payload["ee_version"] == ee.__version__, (
        "tests/fixtures/ee_algorithms.json.gz was captured against "
        f"{payload['ee_version']} but this env runs {ee.__version__}; "
        "re-run tools/capture_ee_algorithms.py"
    )
    assert "Image.where" in payload["algorithms"]


def test_serialize_is_byte_identical_across_rebuilds(ee_offline):
    first = ee.Image(0).where(ee.Image(1).eq(1), 3).serialize()
    second = ee.Image(0).where(ee.Image(1).eq(1), 3).serialize()
    assert first == second
    assert "Image.where" in first


def test_the_algorithm_table_is_load_bearing(tmp_path):
    """An empty table falls through: ee.Image(0).eq(1) has no function to call."""
    script = textwrap.dedent(
        """
        from unittest import mock
        from unittest.mock import MagicMock
        import ee

        creds = MagicMock()
        creds.with_quota_project.return_value = creds
        creds.universe_domain = "googleapis.com"
        with mock.patch.object(ee.data, "getAlgorithms", return_value={}), \\
             mock.patch.object(ee.data, "_install_cloud_api_resource"), \\
             mock.patch.object(ee.deprecation, "InitializeDeprecatedAssets"):
            ee.Initialize(credentials=creds, project="fake-project")
            # ApiFunction.initialize() (ee/apifunction.py:160-171) re-fetches on every
            # lookup miss while cls._api is falsy, and {} is as falsy as "unset" - so an
            # empty table never "sticks" past Initialize(). The mock must still be active
            # for this call, or the retry hits the real (unmocked) getAlgorithms and raises
            # EEException instead of the AttributeError this test is about.
            try:
                ee.Image(0).where(ee.Image(1).eq(1), 3)
            except AttributeError as error:
                print("EMPTY_TABLE_FAILS:", error)
            else:
                print("EMPTY_TABLE_SUCCEEDED")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert "EMPTY_TABLE_FAILS: 'NoneType' object has no attribute 'call'" in result.stdout


def test_initialize_opens_no_socket(tmp_path):
    """The fixture must work in CI with no network and an empty HOME."""
    script = textwrap.dedent(
        """
        import socket
        class Blocked(Exception):
            pass
        def boom(*args, **kwargs):
            raise Blocked("network attempted")

        import sys
        sys.path.insert(0, REPO)
        import ee
        socket.socket = boom
        socket.create_connection = boom

        from tests.ee_offline import initialize_offline_ee, load_ee_algorithms
        initialize_offline_ee(load_ee_algorithms()["algorithms"])
        print("SERIALIZED:", len(ee.Image(0).where(ee.Image(1).eq(1), 3).serialize()))
        """
    )
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", f"REPO={str(repo)!r}\n" + script],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert "SERIALIZED:" in result.stdout
    assert list(tmp_path.iterdir()) == [], "the fixture wrote into HOME"


def test_fixture_is_session_scoped_and_reusable(ee_offline):
    """Requesting it twice must not re-initialize or change the encoding."""
    before = ee.Image(0).where(ee.Image(1).eq(1), 3).serialize()
    after = ee.Image(0).where(ee.Image(1).eq(1), 3).serialize()
    assert before == after
