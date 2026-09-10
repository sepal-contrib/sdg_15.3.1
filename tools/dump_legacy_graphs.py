"""Parity stage A: dump the legacy ee graphs, once, against the legacy tree.

Run this from the repo root while ``component/`` still exists. It has to run as a
module: executed as a path, ``sys.path[0]`` is ``tools/`` and
``from tools.scenarios import SCENARIOS`` raises ModuleNotFoundError.

    python -m tools.dump_legacy_graphs --out tests/golden

For each scenario it writes ``tests/golden/<scenario>/spec.json`` (the RunSpec
that must reproduce it) plus one ``<layer>.json`` per image, or ``error.json`` if
the legacy raised -- a crashing scenario is evidence, not a skip.
``tests/golden/metadata.json`` records ``ee.__version__``, which stage B asserts
before comparing anything (two earthengine-api versions produce different graphs
for reasons unrelated to the port, and the tempting fix is to regenerate the
goldens, which discards the whole guarantee).

Two things this tool does that the plan text does not spell out, both for the
same reason -- stage A and stage B must differ ONLY in which code builds the
graph:

* ``ee`` is initialised from the SAME committed algorithm table the test suite
  uses (``tests/ee_offline.py``). Serialization is client-side, and the fixture
  was captured from this very earthengine-api version, so this records the graph
  the legacy would have sent -- while removing "one side ran against a live
  discovery document and the other against the fixture" as a source of diffs.
  ``--live`` opts back into ``ee.Initialize()`` for anyone who wants to confirm
  that on a machine with credentials.
* The legacy model is built from the spec AFTER it has been round-tripped
  through ``spec.json``, so both stages consume literally the same bytes. Without
  that, a lossy ``to_dict``/``from_dict`` would show up as an engine diff.

This tool imports the legacy, and importing ``component`` runs
``component/parameter/directory.py:6-10``, which mkdirs ``~/module_results``.
That is a recorded legacy defect, expected here, and the reason the TEST SUITE
must never import the legacy.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import UTC, datetime
from pathlib import Path

import ee

from component.scripts.run_15_3_1 import compute_indicator_maps  # type: ignore[import-not-found]
from sdg1531.spec import RunSpec
from tools.scenarios import SCENARIOS
from tools.to_legacy_model import to_legacy_model

# the seven outputs, in the order of indicator_model.py:272-278
LAYERS = (
    "land_cover",
    "soc",
    "productivity",
    "productivity_trend",
    "productivity_state",
    "productivity_performance",
    "indicator_15_3_1",
)


class NullOutput:
    """sw.Alert stand-in: the science calls these and reads nothing back."""

    def add_live_msg(self, *args, **kwargs) -> None:
        return None

    def add_msg(self, *args, **kwargs) -> None:
        return None

    def reset(self, *args, **kwargs) -> None:
        return None


def initialize_ee(live: bool) -> str:
    """Initialise ``ee`` and return the algorithm-table provenance, for metadata.json."""
    if live:
        ee.Initialize()
        return "live"

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from tests.ee_offline import initialize_offline_ee, load_ee_algorithms

    payload = load_ee_algorithms()
    initialize_offline_ee(payload["algorithms"])
    return f"tests/fixtures/ee_algorithms.json.gz (ee {payload['ee_version']})"


def dump_scenario(name: str, out_root: Path) -> str:
    spec = SCENARIOS[name]
    directory = out_root / name
    # a scenario that used to succeed and now raises would otherwise keep its
    # stale <layer>.json files beside the new error.json
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)

    payload = spec.to_dict()
    (directory / "spec.json").write_text(json.dumps(payload, indent=2, sort_keys=True))
    # stage B reads this file, not SCENARIOS; build stage A's model from it too
    spec = RunSpec.from_dict(json.loads((directory / "spec.json").read_text()))

    with tempfile.TemporaryDirectory() as tmp:
        try:
            model, aoi = to_legacy_model(spec, Path(tmp))
            compute_indicator_maps(aoi, model, NullOutput())
        except Exception as exc:  # the crash IS the golden
            (directory / "error.json").write_text(
                json.dumps(
                    {
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(),
                    },
                    indent=2,
                )
            )
            return f"{name}: ERROR {type(exc).__name__}"

        for layer in LAYERS:
            image = getattr(model, layer)
            encoded = ee.serializer.encode(image)
            (directory / f"{layer}.json").write_text(json.dumps(encoded, indent=2, sort_keys=True))
    return f"{name}: ok"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("tests/golden"))
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument(
        "--live",
        action="store_true",
        help="use ee.Initialize() instead of the committed algorithm-table fixture",
    )
    args = parser.parse_args()

    algorithms = initialize_ee(args.live)

    names = args.only or sorted(SCENARIOS)
    args.out.mkdir(parents=True, exist_ok=True)
    for name in names:
        print(dump_scenario(name, args.out))

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    (args.out / "metadata.json").write_text(
        json.dumps(
            {
                "ee_version": ee.__version__,
                "algorithms": algorithms,
                "generated": datetime.now(UTC).isoformat(),
                "legacy_commit": commit,
                "scenarios": sorted(names),
                "layers": list(LAYERS),
            },
            indent=2,
        )
    )
    print(f"metadata: ee {ee.__version__} @ {commit}")


if __name__ == "__main__":
    main()
