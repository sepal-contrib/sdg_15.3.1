import ee 

from component import parameter as pm

ee.Initialize()

def land_cover(io, aoi_io, output):
    """Calculate land cover indicator"""

    # load the land cover map
    landcover = ee.Image(pm.land_cover).clip(aoi_io.get_aoi_ee().geometry().bounds())
    landcover = landcover \
        .where(landcover.eq(9999), pm.int_16_min) \
        .updateMask(landcover.neq(pm.int_16_min))

    # Remap LC according to input matrix, aggregation of land cover classesclasses to IPCC classes.
    lc_year_start = min(max(io.start, pm.lc_first_year), pm.land_use_max_year)
    lc_year_end = min(max(io.end, pm.lc_first_year), pm.land_use_max_year)
    
    # baseline land cover map reclassified into IPCC classes
    landcover_bl_remapped = landcover \
        .select(f'y{lc_year_start}') \
        .remap(pm.translation_matrix[0], pm.translation_matrix[1])
    
    # target land cover map reclassified into IPCC classes
    landcover_tg_remapped = landcover \
            .select(f'y{lc_year_end}') \
            .remap(pm.translation_matrix[0],pm.translation_matrix[1])


    # compute transition map (first digit for baseline land cover, and second digit for target year land cover)
    landcover_transition = landcover_bl_remapped \
            .multiply(10) \
            .add(landcover_tg_remapped)

    # definition of land cover transitions as degradation (-1), improvement (1), or no relevant change (0)
    trans_matrix_flatten = [item for sublist in io.transition_matrix for item in sublist]
    landcover_degredation = landcover_transition \
            .remap(pm.IPCC_lc_change_matrix, trans_matrix_flatten) \
            .rename("degredation")

    # Remap persistence classes so they are sequential.
    landcover_transition = landcover_transition.remap(pm.IPCC_lc_change_matrix, pm.sequential_matrix)    

    # to improve output speed 
    # convert the results into bytes (uint8)
    # 0 nodata - 1 degraded - 2 stable - 3 improved
    landcover_transition = landcover_transition \
        .rename("degredation") \
        .where(-1, 1) \
        .where(0, 2) \
        .where(1, 3) \
        .where(pm.int_16_min, 0) \
        .unmask(0) \
        .uint8()

    return landcover_transition