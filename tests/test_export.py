"""zonal_shapefile_zip returns bytes and leaves no file behind."""

import io
import tempfile
import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from sdg1531.errors import StatisticsError
from sdg1531.export import zonal_shapefile_zip

# ESRI Shapefile is a file SET; these four are the members without which the layer
# cannot be reopened (the geometry, its index, the attribute table and the CRS).
# pyogrio 0.11 writes a fifth, `.cpg`, which is the encoding sidecar.
MANDATORY_MEMBERS = frozenset({"shp", "shx", "dbf", "prj"})


def sample_gdf():
    return gpd.GeoDataFrame(
        {
            "name": ["zone-a", "zone-b"],
            "NoData": [1.23, 0.0],
            "Degrade": [10.5, 5.0],
            "Stable": [20.25, 1.0],
            "Improve": [2.0, 0.0],
        },
        geometry=[
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            Polygon([(2, 2), (3, 2), (3, 3), (2, 3)]),
        ],
        crs="EPSG:4326",
    )


def test_zip_contains_every_mandatory_shapefile_member():
    data = zonal_shapefile_zip(sample_gdf())

    assert isinstance(data, bytes)
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert {n.rsplit(".", 1)[1] for n in names} >= MANDATORY_MEMBERS
    # One layer, at the zip root: run_15_3_1.py:363-365 wrote `file.name`, so a reader
    # that joins the archive root to the .shp name still finds it. A second stem would
    # mean a stale member from an earlier run rode along.
    assert all("/" not in n for n in names), names
    assert {n.rsplit(".", 1)[0] for n in names} == {"zonal"}
    # by name, so the archive is byte-stable across runs on the same frame
    assert names == sorted(names)


def test_the_zip_is_deflated_not_stored():
    """``EXPECTED_DIVERGENCES`` note 2 calls this a deliberate change from the legacy's
    ``ZipFile(path, "w")`` default of ``ZIP_STORED`` (run_15_3_1.py:361). A shapefile's
    .dbf and .shp are highly compressible and the bytes cross the wire to a browser, so
    the divergence is the point -- and it was pinned by nothing.
    """
    data = zonal_shapefile_zip(sample_gdf())

    members = zipfile.ZipFile(io.BytesIO(data)).infolist()
    assert {m.compress_type for m in members} == {zipfile.ZIP_DEFLATED}


def test_the_zip_round_trips_back_into_geopandas():
    data = zonal_shapefile_zip(sample_gdf())

    back = gpd.read_file(io.BytesIO(data))

    assert len(back) == 2
    assert back.crs == "EPSG:4326"
    assert "NoData" in back.columns
    assert back["Degrade"].tolist() == [10.5, 5.0]


def test_it_leaves_nothing_behind_in_the_working_directory(tmp_path, monkeypatch):
    """The ESRI Shapefile driver needs a real directory, so zonal_shapefile_zip
    writes into a TemporaryDirectory that is gone before it returns. What it must
    never do is leave a file where the caller is working: run_15_3_1.py:356-366
    wrote into ~/module_results and left the five members there."""
    monkeypatch.chdir(tmp_path)

    data = zonal_shapefile_zip(sample_gdf())

    assert data
    assert list(tmp_path.iterdir()) == []


def test_it_deletes_the_temporary_directory_it_wrote_into(tmp_path, monkeypatch):
    """Not covered by the cwd test above: ``TemporaryDirectory`` writes under
    ``$TMPDIR``, never the working directory, so a spool that is created and never
    cleaned up leaves the working directory spotless and the container's disk
    filling one run at a time. ``tempfile.tempdir`` is the documented override.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(spool))

    data = zonal_shapefile_zip(sample_gdf())

    assert data
    assert list(spool.iterdir()) == [], list(spool.iterdir())


def test_an_empty_frame_raises_a_domain_error():
    empty = gpd.GeoDataFrame({"name": []}, geometry=[], crs="EPSG:4326")
    with pytest.raises(StatisticsError, match=r"nothing to export"):
        zonal_shapefile_zip(empty)


def test_a_missing_frame_raises_the_same_domain_error():
    """``decode_zonal_areas`` raises rather than returning ``None`` now, but
    run_15_3_1.py:337-340 passed a ``None`` straight through to ``to_file``."""
    with pytest.raises(StatisticsError, match=r"nothing to export"):
        zonal_shapefile_zip(None)


class FakeFrame:
    """A frame whose ``to_file`` does exactly what the test needs.

    pyogrio 0.11 is far too permissive to drive the two failure branches from real
    data -- it happily writes a frame carrying dict, list and null-geometry columns --
    so the driver is stubbed instead. ``zonal_shapefile_zip`` only ever calls ``len``
    and ``to_file`` on its argument, which is why it is annotated ``Any``.
    """

    def __init__(self, error=None):
        self.error = error

    def __len__(self):
        return 1

    def to_file(self, path):
        if self.error is not None:
            raise self.error


def test_a_driver_failure_is_reported_as_a_domain_error():
    """run_15_3_1.py:356 let the driver's own exception escape with no context, and
    its caller at :339-340 replaced it with a generic Exception, discarding the
    traceback. The cause is chained here instead."""
    boom = RuntimeError("no space left on device")

    with pytest.raises(StatisticsError, match=r"Could not write the shapefile") as excinfo:
        zonal_shapefile_zip(FakeFrame(error=boom))

    assert excinfo.value.__cause__ is boom


def test_a_writer_that_produced_no_members_is_reported_as_a_domain_error():
    """Otherwise the caller gets a valid, empty, 22-byte zip and no hint why."""
    with pytest.raises(StatisticsError, match=r"produced no files"):
        zonal_shapefile_zip(FakeFrame())
