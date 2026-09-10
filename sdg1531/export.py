"""Zonal delivery: the domain returns bytes, the app writes them (D12).

The container-local disk is invisible or collides between users, so nothing this
module writes outlives the call. An ESRI Shapefile is a five-file set and pyogrio
refuses to write that set to a BytesIO (pyogrio/raw.py:546), so the members go
into a ``TemporaryDirectory`` that is deleted before the bytes are returned.

``sdg1531/export.py`` is the single entry in the Tier-0 guard's
``FS_EXEMPT_FILES`` (Task 1) for exactly this reason. The in-memory ``/vsimem``
route is deliberately NOT used: it needs ``osgeo.gdal``, which is a separate GDAL
package that no pip install of this project's declared dependencies
(``earthengine-api``, ``pandas``, ``geopandas``) provides.

EXPECTED_DIVERGENCES note -- five divergences from ``run_15_3_1.py:356-366``.
Task 17's parity harness must carry all five:

1. **Behaviour-changing.** The legacy wrote the five members into
   ``~/module_results`` (the directory ``parameter/directory.py:7,10`` creates at
   import) and left them there beside the zip; :func:`zonal_shapefile_zip` writes
   into a ``TemporaryDirectory`` that is gone before it returns and hands the caller
   bytes. Nothing survives the call, and where the zip lands is the app layer's
   decision (D12). This is the entry that covers the whole return-type change.
2. **Behaviour-changing, scoped to member ORDER and to a missing member.** The legacy
   zipped a hard-coded suffix list, ``[".dbf", ".prj", ".shp", ".cpg", ".shx"]``
   (:359), in that order, and ``ZipFile.write`` raised ``FileNotFoundError`` for any
   suffix the driver had not produced. This zips exactly the members the driver
   wrote, sorted by name. The archive is ``ZIP_DEFLATED`` where :361 took
   ``ZipFile``'s ``ZIP_STORED`` default, so the bytes differ; the members inside do
   not.
3. **Behaviour-changing, scoped to the member STEM.** Members are named
   ``zonal.*``; the legacy named them for the run-specific ``indicator_stats`` stem
   (:356). The stem is invisible to a reader -- ``geopandas.read_file`` resolves the
   single ``.shp`` in the archive either way -- but it is visible to a user who
   unzips it.
4. **Behaviour-changing.** An empty or absent frame raises
   :class:`~sdg1531.errors.StatisticsError`. ``decode_zonal_areas`` already rejects an
   empty payload, but it drops LineString zones afterwards without re-checking
   (stats/decode.py:269), so an all-LineString AOI still reaches this function with
   nothing in it. The legacy handed that frame to ``to_file`` and shipped a
   zero-feature shapefile.
5. **Behaviour-changing, scoped to error REPORTING.** A driver failure is re-raised as
   a ``StatisticsError`` chaining the original; at :356 the driver's own exception
   escaped uncaught. On input the legacy wrote successfully the two produce the same
   five members.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from sdg1531.errors import StatisticsError

__all__ = ["zonal_shapefile_zip"]

_LAYER_NAME = "zonal"


def zonal_shapefile_zip(gdf: Any) -> bytes:
    """Serialise a zonal GeoDataFrame to a zipped ESRI Shapefile.

    Replaces run_15_3_1.py:356-366 (``to_file`` into ``~/module_results`` plus a
    ZipFile over five hard-coded suffixes). The temporary directory is gone by the
    time this returns; the caller gets bytes and decides where they land.
    """
    if gdf is None or len(gdf) == 0:
        raise StatisticsError("There is nothing to export: the zonal table is empty.")

    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        try:
            gdf.to_file(directory / f"{_LAYER_NAME}.shp")
        except Exception as exc:
            raise StatisticsError(f"Could not write the shapefile: {exc}") from exc

        members = sorted(p for p in directory.iterdir() if p.is_file())
        if not members:
            raise StatisticsError("The shapefile writer produced no files.")

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for member in members:
                archive.writestr(member.name, member.read_bytes())

    return buffer.getvalue()
