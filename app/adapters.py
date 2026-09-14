"""The only translation between pysepal types and domain types.

``sdg1531`` imports no pysepal: ``InfoFetcher`` is a Protocol declared in
``sdg1531.ports`` over nothing but ``typing``, and pysepal's real
``GEEInterface`` already satisfies it structurally (see ``sdg1531/ports.py``'s
module docstring) -- no wrapper needed there.

What pysepal does NOT hand the domain directly is its AOI selection: an
``AoiResult`` carries a GeoDataFrame, an optional ``ee`` object and other
UI-facing state the domain has no use for. ``to_domain_aoi`` is where that
becomes the domain's ``AoiSpec`` union.

Both libraries define a type called ``AoiSpec`` and they are NOT the same:
pysepal's ``AoiSpec`` (``pysepal.solara.components.aoi.aoi_spec``) is a
serializable record of *how* the user picked; the domain's ``AoiSpec``
(``sdg1531.spec``) is a union of *what* was picked. Only the domain's is
imported by name here, to keep that distinction from leaking.
"""

from __future__ import annotations

from pysepal.solara.components.aoi.aoi_result import AoiResult

from sdg1531.spec import AdminAoi, AoiSpec, AssetAoi, GeoJsonAoi

__all__ = ("to_domain_aoi",)

#: Fallback label when a real selection ever carries an empty name. Every
#: production path (``process_asset``, ``process_draw``) already guarantees a
#: non-empty ``AoiResult.name``, so this exists only to keep the domain's
#: required ``name`` field satisfied if that guarantee is ever violated.
_DEFAULT_AOI_NAME = "aoi"


def to_domain_aoi(result: AoiResult | None) -> AoiSpec | None:
    """pysepal's ``AoiResult`` -> the domain's ``AoiSpec`` union.

    ``None`` in means ``None`` out: an unselected AOI is a normal state before
    the user has chosen, and ``validate()`` is what reports it.

    ``ASSET``, ``DRAW`` and the three ``ADMIN0``/``ADMIN1``/``ADMIN2`` methods
    convert, matching the domain's three ``AoiSpec`` arms. An ADMIN selection
    carries no client-side geometry (``AoiResult.get_gdf_async()`` returns
    ``None`` for GEE results, and ``fetch_admin_bounds_async()`` returns only
    a bounding box), so it becomes ``AdminAoi`` -- the GAUL leaf code, not a
    polygon -- which is enough for ``ExecutionContext.from_aoi_spec`` to
    rebuild the same collection through ``pygaul``. The local-only
    ``SHAPE``/``POINTS`` methods still fall through to ``None``: they have no
    domain arm at all.
    """
    if result is None:
        return None

    name = result.name or _DEFAULT_AOI_NAME

    if result.method == "ASSET":
        asset_id = result.spec.asset_id if result.spec else None
        if asset_id:
            return AssetAoi(asset_id=asset_id, name=name)
        return None

    if result.method == "DRAW":
        geojson = result.spec.geo_json if result.spec else None
        if geojson:
            return GeoJsonAoi(geojson=geojson, name=name)
        return None

    if result.method in ("ADMIN0", "ADMIN1", "ADMIN2"):
        if result.admin:
            return AdminAoi(admin_code=str(result.admin), name=name)
        return None

    return None
