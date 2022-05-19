import ee

from component import parameter as pm

ee.Initialize()


def land_cover(model, aoi_model, output):
    """Calculate land cover sub-indicator"""

    # load the aoi extends
    geom = aoi_model.feature_collection.geometry().bounds()

    # load the land cover map
    landcover = ee.ImageCollection(pm.land_cover_ic)

    # Remap LC according to input matrix, aggregation of land cover classes to IPCC classes.

    landcover_start = (
        landcover.filter(
            ee.Filter.calendarRange(
                model.lc_year_start_esa, model.lc_year_start_esa, "year"
            )
        )
        .first()
        .clip(geom)
        .rename("landcover_start")
    )

    landcover_end = (
        landcover.filter(
            ee.Filter.calendarRange(
                model.lc_year_end_esa, model.lc_year_end_esa, "year"
            )
        )
        .first()
        .clip(geom)
        .rename("landcover_end")
    )

    # create the landcover maps based on the custom one or based on CCI
    if model.start_lc and model.end_lc:

        landcover_start_remapped = ee.Image(model.start_lc).clip(geom).rename("start")
        landcover_end_remapped = ee.Image(model.end_lc).clip(geom).rename("end")

    else:

        # baseline land cover map reclassified into IPCC classes
        landcover_start_remapped = landcover_start.remap(
            pm.translation_matrix[0], pm.translation_matrix[1]
        ).rename("start")

        # target land cover map reclassified into IPCC classes
        landcover_end_remapped = landcover_end.remap(
            pm.translation_matrix[0], pm.translation_matrix[1]
        ).rename("end")

    ## Waterbody data to mask indicators
    if model.start_lc and model.end_lc and model.water_mask_pixel > 9:
        water_body = (
            landcover_end_remapped.eq(int(model.water_mask_pixel))
            .selfMask()
            .rename("water")
        )
    ##to extract the waterbody from the defaul land cover data set
    elif int(model.water_mask_pixel) == 70:
        water_body = landcover_end.eq(210).selfMask().rename("water")
    elif model.water_mask_asset_id and model.water_mask_asset_band:
        water_body = (
            ee.Image(model.water_mask_asset_id)
            .select(model.water_mask_asset_band)
            .selfMask()
            .rename("water")
        )
    else:
        water_body = (
            ee.Image(pm.jrc_water)
            .select("seasonality")
            .gte(int(model.seasonality))
            .selfMask()
            .rename("water")
        )

    # compute transition map (first two digits for historical land cover, and second two digits for monitoring year land cover)
    landcover_transition = (
        landcover_start_remapped.multiply(100)
        .add(landcover_end_remapped)
        .rename("transition")
    )

    # definition of land cover transitions as degradation (-1), improvement (1), or no relevant change (0)

    landcover_degredation = landcover_transition.remap(
        model.lc_class_combination, model.trans_matrix_flatten
    )

    # use the byte convention
    # 1 degraded - 2 stable - 3 improved
    landcover_degredation = (
        landcover_degredation.remap([1, 0, -1, pm.int_16_min], [3, 2, 1, 0])
        .uint16()
        .rename("degradation")
    )

    land_cover_out = (
        landcover_degredation.addBands(landcover_transition.uint16())
        .addBands(landcover_start_remapped.uint16())
        .addBands(landcover_end_remapped.uint16())
        .addBands(water_body.uint16())
    )

    return land_cover_out
