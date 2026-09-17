"""``sdg1531.catalog.SENSORS``' year bounds, held to the real Earth Engine catalogue.

``SensorInfo.first_year``/``last_year`` are hand-typed external facts (see
``catalog.py``'s module docstring): nothing in this repository can derive them,
so they are exactly the kind of roster this project distrusts when it is only
checked against itself. This file is the check against reality -- it asks each
real collection for the year of its own first and last image and asserts the
constant still matches.

Marked ``network`` throughout, so the PR gate (``pytest -m "not network"``) never
selects it and the nightly workflow (``pytest -m network``) is the only thing that
runs it; the round-trip cost (eleven ``getInfo()`` calls, two of them -- Sentinel 2
and every Landsat collection -- against tens of millions of scenes) is real and is
not something a PR should pay.

**Two different claims for two different kinds of bound.** A retired mission's
last image will never move, so ``Landsat 4``, ``Landsat 5``, ``Landsat 7`` and
``Terra NPP`` (USGS-deprecated, receiving no further data -- see catalog.py) get
an EXACT match on both ends. Every other sensor here is still being ingested, so
pinning an exact ``last_year`` would go stale on its own the next time a scene
lands; ``last_year=None`` instead claims "still active", and what is checked is
that claim itself -- the real collection's latest image must be recent, or the
sensor has quietly gone dark and the roster is lying about it. ``first_year`` is
checked exactly for every sensor: a mission's launch date does not move either
way.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path

import ee
import pytest

from sdg1531.catalog import SENSORS, SensorInfo

# A sensor marked `last_year=None` must have produced an image within this many
# years of today, or the "still active" claim is unverified rather than true.
# Wide enough to tolerate a slow-processing pipeline (Landsat 7's own archive
# lags real time by months), tight enough that a mission going dark for good is
# still caught well before the roster becomes a year stale.
_STILL_ACTIVE_WITHIN_YEARS = 2


def _initialize() -> None:
    """``ee.Initialize`` from the ambient credential.

    Copied from ``test_network_smoke.py``'s helper of the same name rather than
    imported: the two files' failure modes are independent (this one must keep
    raising even if the smoke test's credential handling ever changes), which is
    the same reasoning ``sdg1531.validate``'s own ``_clamp_cci`` gives for not
    importing ``resolve``'s copy.

    A missing credential RAISES rather than skipping, for the same reason: a skip
    in the only job that runs this file is indistinguishable from a pass.
    """
    token = os.environ.get("EARTHENGINE_TOKEN")
    credentials = Path.home() / ".config" / "earthengine" / "credentials"
    if token and not credentials.exists():
        credentials.parent.mkdir(parents=True, exist_ok=True)
        credentials.write_text(token)
    if not token and not credentials.exists():
        raise RuntimeError(
            "no Earth Engine credential: set the EARTHENGINE_TOKEN repository secret, "
            f"or write {credentials}. This file fails rather than skipping, because "
            "the nightly job is the only thing that runs it."
        )
    ee.Initialize()


def _real_year_bounds(collection_id: str) -> tuple[int, int]:
    """The year of ``collection_id``'s first and last image, by ``system:time_start``.

    ``limit(1, property, ascending)`` rather than ``sort().first()``: both ends are
    still picked server-side, but a full ``sort()`` over Sentinel 2's tens of
    millions of scenes once timed out Earth Engine's own compute budget
    (``EEException: Computation timed out``, measured running this file's first
    draft) where ``limit()`` -- GEE's documented top-N idiom -- does not, because
    it never has to order the whole collection to answer "which N are smallest".
    """
    collection = ee.ImageCollection(collection_id)
    earliest = ee.Image(collection.limit(1, "system:time_start", True).first())
    latest = ee.Image(collection.limit(1, "system:time_start", False).first())
    lo_ms, hi_ms = ee.List(
        [earliest.get("system:time_start"), latest.get("system:time_start")]
    ).getInfo()
    return _year_of(lo_ms), _year_of(hi_ms)


def _year_of(epoch_ms: float) -> int:
    return datetime.datetime.fromtimestamp(epoch_ms / 1000, tz=datetime.UTC).year


def _collection_ids(info: SensorInfo) -> tuple[str, ...]:
    """``info.collection_id`` as a tuple, whichever shape it is.

    "Derived VI Landsat" carries a pair (catalog.py's own note on why); every
    other sensor carries one id. Both of the pair are checked against the SAME
    recorded bounds -- confirmed empirically before this file was written: the
    NDVI and EVI composite collections report identical first/last years.
    """
    collection_id = info.collection_id
    return collection_id if isinstance(collection_id, tuple) else (collection_id,)


@pytest.mark.network
@pytest.mark.parametrize("name", list(SENSORS))
def test_sensor_year_bounds_match_the_real_collection(name: str) -> None:
    _initialize()
    info = SENSORS[name]

    for collection_id in _collection_ids(info):
        real_first, real_last = _real_year_bounds(collection_id)

        assert real_first == info.first_year, (
            f"{name} ({collection_id}): recorded first_year={info.first_year}, "
            f"the real collection's earliest image is from {real_first}"
        )

        if info.last_year is not None:
            assert real_last == info.last_year, (
                f"{name} ({collection_id}): recorded last_year={info.last_year}, "
                f"the real collection's latest image is from {real_last}"
            )
        else:
            cutoff = datetime.datetime.now(tz=datetime.UTC).year - _STILL_ACTIVE_WITHIN_YEARS
            assert real_last >= cutoff, (
                f"{name} ({collection_id}) is recorded as still active "
                f"(last_year=None), but its latest image is from {real_last} -- "
                f"more than {_STILL_ACTIVE_WITHIN_YEARS} years ago. The mission may "
                "have been retired; give it a real last_year in sdg1531.catalog."
            )


def test_sensor_bounds_fail_loudly_without_a_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The nightly must go red when the secret goes missing, not green and quiet."""
    monkeypatch.delenv("EARTHENGINE_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    with pytest.raises(RuntimeError, match="EARTHENGINE_TOKEN"):
        _initialize()
