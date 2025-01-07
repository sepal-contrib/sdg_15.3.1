from functools import partial

# import json

import ee

from component import parameter as pm


def integrate_climate(aoi_model, model, output):
    start_list = [
        model.start,
        model.trend_start,
        model.state_start,
        model.performance_start,
    ]
    end_list = [model.end, model.trend_end, model.state_end, model.performance_end]
    period_start = min(filter(lambda v: v is not None, start_list))
    period_end = max(filter(lambda v: v is not None, end_list))
    precipitation = (
        ee.ImageCollection(pm.precipitation)
        .filterBounds(aoi_model.feature_collection)
        .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
        .select("precipitation")
    )

    climate_int = int_yearly_climate(precipitation, period_start, period_end)
    return climate_int


def integrate_vi(aoi_model, model, output):
    start_list = [
        model.start,
        model.trend_start,
        model.state_start,
        model.performance_start,
    ]
    end_list = [model.end, model.trend_end, model.state_end, model.performance_end]
    period_start = min(filter(lambda v: v is not None, start_list))
    period_end = max(filter(lambda v: v is not None, end_list))
    ee_asset_list = [
        inner_list[0] for inner_list in (pm.sensors[key] for key in model.sensors)
    ]

    if {"MODIS MOD13Q1", "MODIS MYD13Q1"} & set(model.sensors):
        integrated_vi = process_modis(
            model.sensors,
            ee_asset_list,
            model.vegetation_index,
            model.threshold,
            period_start,
            period_end,
        )
    elif "Terra NPP" in model.sensors:
        integrated_vi = process_terra_npp(ee_asset_list, period_start, period_end)
    elif "Sentinel 2" in model.sensors:
        integrated_vi = process_sentinel2(
            aoi_model.feature_collection,
            model.sensors[0],
            ee_asset_list[0],
            model.vegetation_index,
            model.threshold,
            period_start,
            period_end,
        )
    elif "Derived VI Landsat" in model.sensors:
        asset_id = (
            ee_asset_list[0][0]
            if model.vegetation_index == "ndvi"
            else ee_asset_list[0][1]
        )
        integrated_vi = process_landsat_derived_vi(
            aoi_model.feature_collection,
            asset_id,
            model.threshold,
            period_start,
            period_end,
        )
    elif "GEE Asset" in model.sensors:
        integrated_vi = ee.ImageCollection(model.integrated_vi_asset)
    elif {"Landsat 4", "Landsat 5", "Landsat 7", "Landsat 8", "Landsat 9"} & set(
        model.sensors
    ):
        integrated_vi = process_landsat_sensors(
            aoi_model.feature_collection,
            model.sensors,
            ee_asset_list,
            model.vegetation_index,
            model.threshold,
            period_start,
            period_end,
        )
    else:
        raise ValueError("No valid sensor type found in the model.")
    return integrated_vi


def process_modis(
    sensor_list, ee_asset_list, vi_index, threshold, period_start, period_end
):
    modis_coll_ = ee.ImageCollection(ee_asset_list[0]).filterDate(
        f"{period_start}-01-01", f"{period_end}-12-31"
    )

    # merge the collection if both the MODIS sensors are selected
    if len(sensor_list) > 1:
        modis_coll_ = modis_coll_.merge(
            ee.ImageCollection(ee_asset_list[1]).filterDate(
                f"{period_start}-01-01", f"{period_end}-12-31"
            )
        )
    # Apply the cloud mask
    modis_coll = modis_coll_.map(partial(cloud_mask, sensor="MODIS"))

    if vi_index in ["ndvi", "evi"]:
        modis_vi_scalled = modis_coll.select(vi_index.upper()).map(
            partial(img_scalling, scale_factor=0.0001)
        )
        modis_vi_w_threshold = modis_vi_scalled.map(
            partial(vi_threshold, threshold=threshold)
        )
    elif vi_index == "msvi":
        modis_vi_scalled = modis_coll.map(calculate_msvi_modis).select("msvi")
        modis_vi_w_threshold = modis_vi_scalled.map(
            partial(vi_threshold, threshold=threshold)
        )
    else:
        raise ValueError(f"Unsupported vegetation index: {vi_index}")

    integrated_vi_coll = annual_modis_vi(modis_vi_w_threshold, period_start, period_end)
    return integrated_vi_coll


def process_terra_npp(ee_asset_list, period_start, period_end):
    npp_filtered = (
        ee.ImageCollection(ee_asset_list[0])
        .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
        .select("Npp")
    )
    integrated_vi_coll = preproc_modis_npp(npp_filtered, period_start, period_end)

    return integrated_vi_coll


# todo: need to create a widget to customize the cloud filter value
def process_landsat_sensors(
    aoi, sensor_list, ee_asset_list, vi_index, threshold, period_start, period_end
):
    i_img_coll = ee.ImageCollection([])

    for sensor, asset_id in zip(sensor_list, ee_asset_list):
        sat = (
            ee.ImageCollection(asset_id)
            .filterBounds(aoi)
            .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
            .filter(ee.Filter.lt("CLOUD_COVER_LAND", 20))
            .map(partial(rename_band, sensor=sensor))
            .map(partial(cloud_mask, sensor=sensor))
            .map(partial(apply_scale_factor, sensor=sensor))
        )

        i_img_coll = i_img_coll.merge(sat)

    if vi_index in ["ndvi", "evi", "msvi"]:
        vi_coll = i_img_coll.map(globals()[f"calculate_{vi_index}"]).select(
            vi_index.lower()
        )
        vi_coll_w_threshold = vi_coll.map(partial(vi_threshold, threshold=threshold))
        integrated_vi_coll = int_yearly_ndvi(
            vi_coll_w_threshold, period_start, period_end
        )
    else:
        raise ValueError(f"Unsupported vegetation index: {vi_index}")

    return integrated_vi_coll


# todo: need to create a widget to customize the cloud filter value
def process_sentinel2(
    aoi, sensor, ee_asset_id, vi_index, threshold, period_start, period_end
):
    i_img_coll = (
        ee.ImageCollection(ee_asset_id)
        .filterBounds(aoi)
        .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .map(partial(rename_band, sensor=sensor))
        .map(partial(cloud_mask, sensor=sensor))
        .map(partial(apply_scale_factor, sensor=sensor))
    )

    if vi_index in ["ndvi", "evi", "msvi"]:
        vi_coll = i_img_coll.map(globals()[f"calculate_{vi_index}"]).select(
            vi_index.lower()
        )
        vi_coll_w_threshold = vi_coll.map(partial(vi_threshold, threshold=threshold))
        integrated_vi_coll = int_yearly_ndvi(
            vi_coll_w_threshold, period_start, period_end
        )
    else:
        raise ValueError(f"Unsupported vegetation index: {vi_index}")

    return integrated_vi_coll


def process_landsat_derived_vi(aoi, asset_id, threshold, period_start, period_end):
    img_coll = (
        ee.ImageCollection(asset_id)
        .filterBounds(aoi)
        .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
        .map(partial(vi_threshold, threshold=threshold))
    )
    integrated_vi_coll = annual_modis_vi(img_coll, period_start, period_end)
    return integrated_vi_coll


def process_climate_data(aoi_model, period_start, period_end):
    precipitation = (
        ee.ImageCollection(pm.precipitation)
        .filterBounds(aoi_model.feature_collection)
        .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
        .select("precipitation")
    )

    climate_int = int_yearly_climate(precipitation, period_start, period_end)

    return climate_int


def rename_band(img, sensor):
    if sensor in ["Landsat 4", "Landsat 5", "Landsat 7"]:
        img = img.select(
            ["SR_B1", "SR_B3", "SR_B4", "QA_PIXEL"], ["Blue", "Red", "NIR", "pixel_qa"]
        )
    elif sensor in ["Landsat 8", "Landsat 9"]:
        img = img.select(
            ["SR_B2", "SR_B4", "SR_B5", "QA_PIXEL"], ["Blue", "Red", "NIR", "pixel_qa"]
        )
    elif sensor == "Sentinel 2":
        img = img.select(["B2", "B4", "B8", "QA60"], ["Blue", "Red", "NIR", "QA60"])

    return img


def cloud_mask(img, sensor):
    """mask the clouds based on the sensor name, sentine 2 data will be multiplyed by 10000 to meet the scale of landsat data"""

    if sensor in ["Landsat 5", "Landsat 7", "Landsat 4", "Landsat 8", "Landsat 9"]:
        qa = img.select("pixel_qa")
        # If the cloud bit (3) is set and the cloud confidence (8) is high
        # or the cloud shadow bit is set (4), then it's a bad pixel.
        cloud = (
            qa.bitwiseAnd(1 << 3).And(qa.bitwiseAnd(1 << 8)).Or(qa.bitwiseAnd(1 << 4))
        )
        # Remove edge pixels that don't occur in all bands
        mask2 = img.mask().reduce(ee.Reducer.min())

        img = img.updateMask(cloud.Not()).updateMask(mask2)

    elif sensor == "Sentinel 2":
        qa = img.select("QA60")
        # Bits 10 and 11 are clouds and cirrus, respectively.
        cloudBitMask = 1 << 10
        cirrusBitMask = 1 << 11
        # Both flags should be set to zero, indicating clear conditions.
        mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))
        img = (
            img.updateMask(mask)
            .divide(10000)
            .copyProperties(img, ["system:time_start", "system:time_end"])
        )
    elif sensor == "MODIS":
        qa = img.select("DetailedQA")
        viqamask1 = bit_selection(qa, 0, 1).lte(1)
        snowmask = bit_selection(qa, 14, 14).eq(0)
        shadowmask = bit_selection(qa, 15, 15).eq(0)
        mixedcloudmask = bit_selection(qa, 10, 10).eq(0)
        mask = viqamask1.And(snowmask).And(shadowmask).And(mixedcloudmask)
        img = img.updateMask(mask)

    return img


def bit_selection(bitmask, start_bit, end_bit):
    bit_len = ee.Number(1).add(end_bit).subtract(start_bit)
    bit_position = ee.Number(1).leftShift(bit_len).subtract(1)
    return bitmask.rightShift(start_bit).bitwiseAnd(bit_position)


def apply_scale_factor(img, sensor):
    """Applies scaling factors to Landsat collection 2"""
    if sensor in ["Landsat 5", "Landsat 7", "Landsat 4", "Landsat 8", "Landsat 9"]:
        scalled_img = (
            img.multiply(0.0000275)
            .add(-0.2)
            .copyProperties(img, ["system:time_start", "system:time_end"])
        )
    elif sensor == "Sentinel 2":
        scalled_img = img.multiply(0.0001).copyProperties(
            img, ["system:time_start", "system:time_end"]
        )
    return scalled_img


def int_yearly_ndvi(ndvi_coll, start, end):
    """Function to integrate observed NDVI datasets at the annual level"""

    def daily_to_monthly_to_annual(year):
        ndvi_collection = ndvi_coll
        ndvi_coll_ann = ndvi_collection.filter(
            ee.Filter.calendarRange(year, field="year")
        )
        months = (
            ndvi_coll_ann.aggregate_array("system:time_start")
            .map(lambda x: ee.Number.parse(ee.Date(x).format("MM")))
            .distinct()
        )

        img_coll = ee.ImageCollection.fromImages(
            months.map(
                lambda month: ndvi_coll_ann.filter(
                    ee.Filter.calendarRange(month, field="month")
                ).reduce(ee.Reducer.mean())
            )
        )
        img_coll_ndvi = (
            img_coll.reduce(ee.Reducer.mean()).float().rename("vi").set("year", year)
        )
        return img_coll_ndvi

    years = ee.List.sequence(start, end)
    img_coll = ee.ImageCollection.fromImages(years.map(daily_to_monthly_to_annual))

    return img_coll


def int_yearly_climate(precipitation, start, end):
    """Function to integrate observed precipitation datasets at the annual level"""

    years = ee.List.sequence(start, end)

    img_coll = ee.ImageCollection.fromImages(
        years.map(
            lambda year: precipitation.filter(
                ee.Filter.calendarRange(year, field="year")
            )
            .reduce(ee.Reducer.mean())
            .rename("clim")
            .addBands(ee.Image().constant(year).float().rename("year"))
            .set("year", year)
        )
    )
    return img_coll


def calculate_ndvi(img):
    """compute the ndvi on renamed bands"""

    red = img.select("Red")
    nir = img.select("NIR")

    ndvi = (
        nir.subtract(red)
        .divide(nir.add(red))
        .rename("ndvi")
        .set("system:time_start", img.get("system:time_start"))
    )

    return ndvi


def calculate_evi(img):
    """compute the enhnce vegetation index on the renamed band"""

    evi = (
        img.expression(
            "2.4*((nir-red)/(nir+red+1))",
            {"nir": img.select("NIR"), "red": img.select("Red")},
        )
        .rename("evi")
        .set("system:time_start", img.get("system:time_start"))
    )
    return evi


def calculate_msvi(img):
    msvi2 = (
        img.expression(
            "(2 * nir + 1 - sqrt(pow((2 * nir + 1), 2) - 8 * (nir - red)) ) / 2",
            {"nir": img.select("NIR"), "red": img.select("Red")},
        )
        .rename("msvi")
        .set("system:time_start", img.get("system:time_start"))
    )
    return msvi2


def calculate_msvi_modis(img):
    msvi2 = (
        img.expression(
            "(2 * nir + 1 - sqrt(pow((2 * nir + 1), 2) - 8 * (nir - red)) ) / 2",
            {"nir": img.select("sur_refl_b02"), "red": img.select("sur_refl_b01")},
        )
        .rename("msvi")
        .set("system:time_start", img.get("system:time_start"))
    )
    return msvi2


def vi_threshold(img, threshold):
    """function to scale and apply vi threshold"""
    threshold_bin = img.gt(threshold)
    return img.multiply(threshold_bin).copyProperties(
        img, ["system:time_start", "system:time_end"]
    )


def img_scalling(img, scale_factor):
    return img.multiply(scale_factor).copyProperties(
        img, ["system:time_start", "system:time_end"]
    )


def annual_modis_vi(modis_img, start, end):
    """Function to integrate observed precipitation datasets at the annual level"""

    years = ee.List.sequence(start, end)

    img_coll = ee.ImageCollection.fromImages(
        years.map(
            lambda year: modis_img.filter(ee.Filter.calendarRange(year, field="year"))
            .reduce(ee.Reducer.mean())
            .rename("vi")
            .addBands(ee.Image().constant(year).float().rename("year"))
            .set("year", year)
        )
    )
    return img_coll


def preproc_modis_npp(npp_coll, start, end):
    years = ee.List.sequence(start, end)
    img_coll = ee.ImageCollection.fromImages(
        years.map(
            lambda year: npp_coll.filter(ee.Filter.calendarRange(year, field="year"))
            .first()
            .multiply(0.0001)
            .rename("vi")
            .addBands(ee.Image().constant(year).float().rename("year"))
            .set("year", year)
        )
    )
    return img_coll
