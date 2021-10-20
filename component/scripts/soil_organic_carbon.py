import ee

ee.Initialize()

from component import parameter as pm


def soil_organic_carbon(model, aoi_model, output):
    """Calculate soil organic carbon indicator"""

    soc = ee.Image(pm.soc).clip(aoi_model.feature_collection.geometry().bounds())
    soc = soc.updateMask(soc.neq(pm.int_16_min))

    lc = (
        ee.Image(pm.land_cover)
        .clip(aoi_model.feature_collection.geometry().bounds())
        .select(ee.List.sequence(model.start - 1992, pm.land_cover_max_year - 1992, 1))
    )

    lc = lc.where(lc.eq(9999), pm.int_16_min).updateMask(lc.neq(pm.int_16_min))

    if not model.conversion_coef:
        ipcc_climate_zones = ee.Image(pm.ipcc_climate_zones).clip(
            aoi_model.feature_collection.geometry().bounds()
        )
        climate_conversion_coef = ipcc_climate_zones.remap(
            pm.climate_conversion_matrix[0], pm.climate_conversion_matrix[1]
        )
    else:
        climate_conversion_coef = model.conversion_coef

    # compute the soc change for the first two years
    lc_time0 = lc.select(0).remap(pm.translation_matrix[0], pm.translation_matrix[1])

    lc_time1 = lc.select(1).remap(pm.translation_matrix[0], pm.translation_matrix[1])

    # compute transition map for the first two years(1st digit for baseline land cover, 2nd for target land cover)
    lc_transition = lc_time0.multiply(10).add(lc_time1)

    # compute raster to register years since transition for the first and second year
    lc_transition_time = ee.Image(2).where(lc_time0.neq(lc_time1), 1)

    # store change factor for land use
    # 333 and -333 will be recoded using the chosen climate coef.
    lc_transition_climate_coef_tmp = lc_transition.remap(
        pm.IPCC_lc_change_matrix, pm.c_conversion_factor
    )
    lc_transition_climate_coef = lc_transition_climate_coef_tmp.where(
        lc_transition_climate_coef_tmp.eq(333), climate_conversion_coef
    ).where(
        lc_transition_climate_coef_tmp.eq(-333),
        ee.Image(1).divide(climate_conversion_coef),
    )

    # store change factor for management regime
    lc_transition_management_factor = lc_transition.remap(
        pm.IPCC_lc_change_matrix, pm.management_factor
    )

    # store change factor for input of organic matter
    lc_transition_organic_factor = lc_transition.remap(
        pm.IPCC_lc_change_matrix, pm.input_factor
    )

    organic_carbon_change = soc.subtract(
        soc.multiply(lc_transition_climate_coef)
        .multiply(lc_transition_management_factor)
        .multiply(lc_transition_organic_factor)
    ).divide(20)

    # compute final soc for the period
    soc_time1 = soc.subtract(organic_carbon_change)

    # add to land cover and soc to stacks from both dates for the first period
    lc_images = ee.Image(lc_time0).addBands(lc_time1)

    soc_images = ee.Image(soc).addBands(soc_time1)

    # Compute the soc change for the rest of  the years
    # years = ee.List.sequence(1, model.end - model.start)
    # soc_images = years.itterate(compute_soc, soc_images)

    for year_index in range(1, pm.land_cover_max_year - model.start):
        lc_time0 = lc.select(year_index).remap(
            pm.translation_matrix[0], pm.translation_matrix[1]
        )

        lc_time1 = lc.select(year_index + 1).remap(
            pm.translation_matrix[0], pm.translation_matrix[1]
        )

        lc_transition_time = lc_transition_time.where(
            lc_time0.eq(lc_time1), lc_transition_time.add(ee.Image(1))
        ).where(lc_time0.neq(lc_time1), ee.Image(1))

        # compute transition map (1st digit for baseline land cover, 2nd for target land cover)
        # But only update where changes acually occured.
        lc_transition_temp = lc_time0.multiply(10).add(lc_time1)
        lc_transition = lc_transition.where(lc_time0.neq(lc_time1), lc_transition_temp)

        # stock change factor for land use
        # 333 and -333 will be recoded using the choosen climate coef.
        lc_transition_climate_coef_tmp = lc_transition.remap(
            pm.IPCC_lc_change_matrix, pm.c_conversion_factor
        )
        lc_transition_climate_coef = lc_transition_climate_coef_tmp.where(
            lc_transition_climate_coef_tmp.eq(333), climate_conversion_coef
        ).where(
            lc_transition_climate_coef_tmp.eq(-333),
            ee.Image(1).divide(climate_conversion_coef),
        )

        # stock change factor for management regime
        lc_transition_management_factor = lc_transition.remap(
            pm.IPCC_lc_change_matrix, pm.management_factor
        )

        # Stock change factor for input of organic matter
        lc_transition_organic_factor = lc_transition.remap(
            pm.IPCC_lc_change_matrix, pm.input_factor
        )

        organic_carbon_change = organic_carbon_change.where(
            lc_time0.neq(lc_time1),
            soc_images.select(year_index)
            .subtract(
                soc_images.select(year_index)
                .multiply(lc_transition_climate_coef)
                .multiply(lc_transition_management_factor)
                .multiply(lc_transition_organic_factor)
            )
            .divide(20),
        ).where(lc_transition_time.gt(20), 0)

        soc_final = soc_images.select(year_index).subtract(organic_carbon_change)

        lc_images = lc_images.addBands(lc_time1)

        soc_images = soc_images.addBands(soc_final)

    # Compute soc percent change for the analysis period
    soc_percent_change = (
        soc_images.select(pm.land_cover_max_year - model.start)
        .subtract(soc_images.select(0))
        .divide(soc_images.select(0))
        .multiply(100)
    )

    # use the bytes convention
    # 1 degraded - 2 stable - 3 improved
    soc_class = (
        ee.Image(0)
        .where(soc_percent_change.gt(10), 3)
        .where(soc_percent_change.lt(10).And(soc_percent_change.gt(-10)), 2)
        .where(soc_percent_change.lt(-10), 1)
        .rename("soc")
        .uint8()
    )

    return soc_class
