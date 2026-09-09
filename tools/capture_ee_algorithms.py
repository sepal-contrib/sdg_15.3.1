"""Capture `ee.data.getAlgorithms()` to a committed fixture.

Spec §12 Tier 3: the offline `ee` fixture needs a real algorithm table. With an
empty table `ee.Image(0).where(...)` raises `AttributeError: 'NoneType' object
has no attribute 'call'`, because `ApiFunction.lookupInternal` returns None
(ee/apifunction.py:145-155) — so the table is load-bearing, not decoration.

This tool needs credentials and network. Run it by hand when the pinned
earthengine-api version changes; CI never runs it (spec §13 risk 5).

Run:  python tools/capture_ee_algorithms.py --project <your-gcp-project>
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import ee


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="GCP project for ee.Initialize")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/fixtures/ee_algorithms.json.gz"),
    )
    args = parser.parse_args()

    ee.Initialize(project=args.project)
    algorithms = ee.data.getAlgorithms()
    payload = {"ee_version": ee.__version__, "algorithms": algorithms}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    # mtime=0 so re-capturing an unchanged table produces an unchanged file
    with gzip.GzipFile(filename="", mode="wb", fileobj=args.out.open("wb"), mtime=0) as fh:
        fh.write(body)

    print(f"wrote {args.out}: {len(algorithms)} algorithms, ee {ee.__version__}")


if __name__ == "__main__":
    main()
