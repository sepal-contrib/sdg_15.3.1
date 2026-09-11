"""Initialise `ee` offline, for graph-shape and parity tests (Tier 3).

Three private behaviours of earthengine-api 1.6.14 are relied on here. When one
of them moves, this file breaks and Tiers 3 and 4 break with it — that is a
fixture regression, not a domain regression -- a known and accepted risk of
building graph tests on private `ee` internals.

1. `ee.Initialize(credentials=...)` only duck-types the credential: it reads
   `.quota_project_id`, calls `.with_quota_project(None)` and reads
   `.universe_domain`. A MagicMock configured to return itself satisfies it.
2. `ee.data._install_cloud_api_resource` fetches the API discovery document over
   the network (ee/_cloud_api_utils.py:200-217, `static_discovery=False`).
   Nothing here ever executes a graph, only serializes one, so it is patched out.
3. `ee.deprecation.InitializeDeprecatedAssets` fetches the STAC catalogue and
   merely warns on failure; it is patched out to keep the run silent and offline.

The captured `getAlgorithms` table is load-bearing: with an empty dict,
`ApiFunction.lookupInternal` returns None and `.eq()` raises AttributeError.
Re-capture it with `tools/capture_ee_algorithms.py`.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any
from unittest import mock
from unittest.mock import MagicMock

import ee

FIXTURE = Path(__file__).parent / "fixtures" / "ee_algorithms.json.gz"


def load_ee_algorithms() -> dict[str, Any]:
    """Return {"ee_version": str, "algorithms": dict} from the committed fixture."""
    payload: dict[str, Any] = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    return payload


def fixture_provenance() -> str:
    """What algorithm table `initialize_offline_ee` would install, as one string.

    Recorded into `tests/golden/metadata.json` by stage A and asserted by stage B
    before it compares anything, the way `ee_version` already is. The algorithm
    signatures shape argument names and value promotion during client-side
    serialization, so a stage-A run against a live discovery document rather than
    this fixture is the same hazard the `ee_version` assert exists to catch.

    This is a NAME, not a fingerprint: both halves of it -- the path and the version
    string inside the fixture -- come from the same committed file, so a fixture
    re-captured with different contents at the same `ee` version produces the same
    provenance. `fixture_digest` is the half that can tell.
    """
    return f"{FIXTURE.relative_to(FIXTURE.parents[2]).as_posix()} (ee {load_ee_algorithms()['ee_version']})"


def fixture_digest() -> str:
    """The sha256 of the committed algorithm table, as recorded beside the goldens.

    What makes `test_the_recorded_algorithm_table_is_the_one_this_environment_installs`
    true to its name: the provenance string is derived from the fixture's own
    contents, so it agrees with itself however the fixture was captured, while this
    is over the bytes. Digesting the compressed file rather than the decoded payload
    is deliberate -- the compressed bytes are what the repository stores and what a
    re-capture would replace.
    """
    return hashlib.sha256(FIXTURE.read_bytes()).hexdigest()


def initialize_offline_ee(algorithms: dict[str, Any]) -> None:
    """Initialise `ee` with a fake credential and a captured algorithm table."""
    ee.Reset()

    credentials = MagicMock()
    credentials.with_quota_project.return_value = credentials
    credentials.universe_domain = "googleapis.com"

    with (
        mock.patch.object(ee.data, "getAlgorithms", return_value=algorithms),
        mock.patch.object(ee.data, "_install_cloud_api_resource"),
        mock.patch.object(ee.deprecation, "InitializeDeprecatedAssets"),
    ):
        # `project` must be passed: this fork of ee.Initialize otherwise opens
        # the persistent credentials file under HOME (ee/__init__.py:190-191).
        ee.Initialize(credentials=credentials, project="fake-project")
