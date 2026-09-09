"""The async wrappers, driven by a FakeFetcher. No network, no pysepal."""

import inspect
from typing import Any

import ee
import geopandas as gpd
import pandas as pd
import pytest
from helpers_stats import FakeFetcher, FakeResolved, StubMaps, load_fixture, make_ctx, make_zones

from sdg1531.engine.context import ExecutionContext
from sdg1531.enums import IndicatorLayer
from sdg1531.errors import StatisticsError
from sdg1531.ports import InfoFetcher
from sdg1531.stats.api import (
    _ZONAL_LABELS,
    fetch_areas_by_land_cover,
    fetch_band_names,
    fetch_distinct_pixel_values,
    fetch_transition_areas,
    fetch_zonal_areas,
)
from tests.engine.graph import _selected_bands, count_calls


class RaisingFetcher:
    """The other half of the port's error surface.

    ``GEEInterface.get_info_async`` logs and RE-RAISES (gee_interface.py:203-205);
    only the batch path hands an Exception back as a value. ``FakeFetcher`` covers
    the value shape, this covers the raise.
    """

    def __init__(self, error: BaseException) -> None:
        self.error = error

    async def get_info_async(self, ee_object: Any = None, tag: Any = None) -> Any:
        raise self.error

    async def get_info_batch_async(self, ee_objects: list[Any]) -> list[Any]:
        return [await self.get_info_async(obj) for obj in ee_objects]


class WideFetcher:
    """A fetcher shaped like the REAL implementor, third defaulted parameter and all.

    pysepal's ``GEEInterface.get_info_async`` takes ``serialized_object=None``
    (gee_interface.py:194) and satisfies ``InfoFetcher`` regardless, because a
    Protocol allows extra parameters that have defaults. Nothing calls this class --
    it exists so the conformance check below cannot regress to an equality that would
    reject the one implementor the port was written for.
    """

    async def get_info_async(
        self, ee_object: Any = None, tag: Any = None, serialized_object: Any = None
    ) -> Any: ...

    async def get_info_batch_async(self, ee_objects: list[Any]) -> list[Any]: ...


@pytest.fixture()
def ctx() -> ExecutionContext:
    return make_ctx()


def _params(func) -> list[str]:
    """The positional-or-keyword parameter names of `func`, minus `self`."""
    return [
        name
        for name, parameter in inspect.signature(func).parameters.items()
        if name != "self" and parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]


@pytest.mark.parametrize("fetcher_class", [FakeFetcher, RaisingFetcher, WideFetcher])
def test_the_test_fetchers_satisfy_the_protocol(fetcher_class) -> None:
    """Structural conformance, checked at RUNTIME.

    An annotation in a test file would prove nothing: mypy is configured over
    ``sdg1531`` only (pyproject.toml ``files = ["sdg1531"]``), so it never reads
    this module. This walks the Protocol's own members instead -- the names, the
    coroutine-ness, and the parameter NAMES, which ``sdg1531/ports.py`` calls
    load-bearing because a Protocol matches positional-or-keyword parameters by
    name.

    The declared names must be a PREFIX of the implemented ones, not equal to them:
    a Protocol is satisfied by an implementor that takes further parameters as long
    as they have defaults, and the real implementor does exactly that -- see
    :class:`WideFetcher`. Demanding equality would reject ``GEEInterface`` itself.

    That real implementor is pysepal's ``GEEInterface``, which the suite may not
    import (Tier-0 isolation); ``sdg1531/ports.py`` records the signatures this was
    written against, pysepal 3.8.3 ``gee_interface.py:193`` and ``:207``.
    """
    attrs = sorted(InfoFetcher.__protocol_attrs__)
    assert attrs == ["get_info_async", "get_info_batch_async"]

    for name in attrs:
        declared = _params(getattr(InfoFetcher, name))
        implemented = getattr(fetcher_class, name, None)
        assert implemented is not None, f"{fetcher_class.__name__} has no {name}"
        assert inspect.iscoroutinefunction(implemented), name
        assert _params(implemented)[: len(declared)] == declared, name


@pytest.mark.asyncio
async def test_fetch_transition_areas_builds_awaits_and_decodes(ctx: ExecutionContext) -> None:
    fetcher = FakeFetcher([load_fixture("transition_areas.json")])
    maps = StubMaps(resolved=FakeResolved(start_year=2004, end_year=2019))

    df = await fetch_transition_areas(fetcher, maps, ctx)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 5
    # the year columns come off maps.resolved, so this also pins that the wrapper
    # threads the run's own spec into the decoder rather than a default
    assert list(df.columns) == [2004, 2019, "Area"]
    assert len(fetcher.calls) == 1
    assert isinstance(fetcher.calls[0], ee.Dictionary)
    assert _selected_bands(fetcher.calls[0]) == {"transition"}


@pytest.mark.asyncio
async def test_fetch_areas_by_land_cover_passes_the_layer_through(ctx: ExecutionContext) -> None:
    fetcher = FakeFetcher([load_fixture("areas_by_land_cover.json")])

    df = await fetch_areas_by_land_cover(
        fetcher, StubMaps(resolved=FakeResolved()), ctx, layer=IndicatorLayer.INDICATOR_15_3_1
    )

    assert list(df.columns) == ["landcover", "indicator_15_3_1", "Area"]
    assert len(df) == 5
    # the layer reached the REQUEST too, not just the column name
    assert _selected_bands(fetcher.calls[0]) == {"start"}


@pytest.mark.asyncio
async def test_fetch_areas_by_land_cover_carries_the_five_level_vocabulary_end_to_end(
    ctx: ExecutionContext,
) -> None:
    """The band on the wire and the legend in the frame are both the 5-level ones."""
    fetcher = FakeFetcher([{"groups": [{"indicator": 4, "groups": [{"lc": 10, "sum": 3.0}]}]}])

    df = await fetch_areas_by_land_cover(
        fetcher, StubMaps(resolved=FakeResolved()), ctx, layer=IndicatorLayer.PRODUCTIVITY_STATE
    )

    assert _selected_bands(fetcher.calls[0]) == {"start", "state_5_levels"}
    assert df.iloc[0]["productivity_state"] == "Potentially improving"


@pytest.mark.asyncio
async def test_a_missing_groups_key_raises_statistics_error(ctx: ExecutionContext) -> None:
    fetcher = FakeFetcher([{}])
    with pytest.raises(StatisticsError, match=r"no 'groups' for land cover transitions"):
        await fetch_transition_areas(fetcher, StubMaps(resolved=FakeResolved()), ctx)


@pytest.mark.asyncio
async def test_an_empty_group_list_decodes_to_an_empty_frame(ctx: ExecutionContext) -> None:
    """An AOI with no pixels of a class is not an error: ``groups: []`` is a valid,
    empty table, and only a MISSING ``groups`` key means the reduction failed."""
    fetcher = FakeFetcher([{"groups": []}])

    df = await fetch_transition_areas(fetcher, StubMaps(resolved=FakeResolved()), ctx)

    assert df.empty
    assert list(df.columns) == [2001, 2015, "Area"]


@pytest.mark.asyncio
async def test_an_exception_payload_is_chained_not_swallowed(ctx: ExecutionContext) -> None:
    """gee_interface.py:210 gathers with return_exceptions=True, so a fetcher can
    hand back an Exception instance instead of raising it."""
    boom = RuntimeError("EEException: User memory limit exceeded")
    fetcher = FakeFetcher([boom])

    with pytest.raises(StatisticsError, match=r"memory limit") as excinfo:
        await fetch_transition_areas(fetcher, StubMaps(resolved=FakeResolved()), ctx)

    assert excinfo.value.__cause__ is boom
    assert "land cover transitions" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_raised_fetcher_error_reaches_the_caller_unchanged(ctx: ExecutionContext) -> None:
    """The single-call path RAISES (gee_interface.py:203-205), and is not wrapped.

    Pinned rather than assumed: the app layer has to catch the Earth Engine error
    itself, not only StatisticsError. Only the returned-as-a-value shape becomes a
    StatisticsError, and that is what ``_unwrap`` exists for.
    """
    boom = RuntimeError("EEException: Computation timed out.")

    with pytest.raises(RuntimeError, match=r"timed out") as excinfo:
        await fetch_transition_areas(RaisingFetcher(boom), StubMaps(resolved=FakeResolved()), ctx)

    assert excinfo.value is boom


@pytest.mark.asyncio
async def test_fetch_zonal_areas_guards_the_feature_count() -> None:
    zones = make_zones()
    fetcher = FakeFetcher([12000])

    with pytest.raises(StatisticsError, match=r"12000 features") as excinfo:
        await fetch_zonal_areas(fetcher, StubMaps(resolved=FakeResolved()), zones, scale=300)

    assert "5000" in str(excinfo.value)
    assert len(fetcher.calls) == 1  # the expensive request was never sent
    # the one call that WAS made is the cheap size probe, not the mapped collection
    assert count_calls(fetcher.calls[0], "Collection.size") == 1
    assert count_calls(fetcher.calls[0], "Collection.map") == 0


@pytest.mark.asyncio
async def test_fetch_zonal_areas_decodes_the_feature_collection() -> None:
    zones = make_zones()
    fetcher = FakeFetcher([2, load_fixture("zonal_features.json")])

    gdf = await fetch_zonal_areas(fetcher, StubMaps(resolved=FakeResolved()), zones, scale=300)

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 2
    # the legacy spellings, each on its own class (run_15_3_1.py:343-350). Asserting
    # the VALUES and not just the column names is what catches a transposed table.
    assert [gdf.iloc[0][name] for name in ("NoData", "Degrade", "Stable", "Improve")] == [
        1.23,
        10.5,
        20.25,
        2.0,
    ]
    # and their ORDER is the legacy's -- :343-350 adds Class_0, Class_3, Class_2,
    # Class_1, which is the field order of the shapefile Task 18 writes. Sorting
    # _ZONAL_LABELS would reorder fields users have tooling keyed on, with every
    # value assertion above still green.
    assert [c for c in gdf.columns if c in set(_ZONAL_LABELS.values())] == [
        "NoData",
        "Improve",
        "Stable",
        "Degrade",
    ]
    # the second call is the mapped collection, sent only after the probe came back
    assert len(fetcher.calls) == 2
    assert count_calls(fetcher.calls[1], "Collection.map") == 1


@pytest.mark.asyncio
async def test_fetch_zonal_areas_accepts_a_collection_at_the_limit() -> None:
    """The guard is `> 5000`, so exactly 5000 features still goes through."""
    fetcher = FakeFetcher([5000, load_fixture("zonal_features.json")])

    gdf = await fetch_zonal_areas(
        fetcher, StubMaps(resolved=FakeResolved()), make_zones(), scale=300
    )

    assert len(gdf) == 2


@pytest.mark.asyncio
async def test_fetch_distinct_pixel_values_and_band_names() -> None:
    fetcher = FakeFetcher([["30", "10"], ["b1", "b2"]])

    assert await fetch_distinct_pixel_values(fetcher, "users/x/a") == (10, 30)
    assert await fetch_band_names(fetcher, "users/x/a") == ("b1", "b2")


@pytest.mark.asyncio
async def test_fetch_band_names_keeps_earth_engines_own_order() -> None:
    """select_lc.py:63-65 natsorted the list before showing it; ordering for display
    is the app layer's (spec §4), so the port hands back what Earth Engine sent."""
    fetcher = FakeFetcher([["b10", "b2", "b1"]])

    assert await fetch_band_names(fetcher, "users/x/a") == ("b10", "b2", "b1")


@pytest.mark.asyncio
async def test_fetch_band_names_rejects_a_null_payload() -> None:
    fetcher = FakeFetcher([None])
    with pytest.raises(StatisticsError, match=r"no band names for users/x/a"):
        await fetch_band_names(fetcher, "users/x/a")
