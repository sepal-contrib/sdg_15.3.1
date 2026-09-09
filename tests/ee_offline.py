"""Initialise `ee` offline, for graph-shape and parity tests (spec §12 Tier 3).

Three private behaviours of earthengine-api 1.6.14 are relied on here. When one
of them moves, this file breaks and Tiers 3 and 4 break with it — that is a
fixture regression, not a domain regression (spec §13 risk 5).

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
import json
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import ee

FIXTURE = Path(__file__).parent / "fixtures" / "ee_algorithms.json.gz"


def load_ee_algorithms() -> dict:
    """Return {"ee_version": str, "algorithms": dict} from the committed fixture."""
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def initialize_offline_ee(algorithms: dict) -> None:
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
