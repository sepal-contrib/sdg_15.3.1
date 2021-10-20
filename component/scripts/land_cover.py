import ee 

from component import parameter as pm

ee.Initialize()

def land_cover(model, aoi_model, output):
    """Calculate land cover indicator"""

    # load the land cover map
    landcover = ee.Image(pm.land_cover).clip(aoi_model.feature_collection.geometry().bounds())
    landcover = landcover \
        .where(landcover.eq(9999), pm.int_16_min) \
        .updateMask(landcover.neq(pm.int_16_min))

    # Remap LC according to input matrix, aggregation of land cover classesclasses to IPCC classes.
    lc_year_start = min(max(model.start, pm.lc_first_year), pm.land_use_max_year)
    lc_year_end = min(max(model.end, pm.lc_first_year), pm.land_use_max_year)
    
    # baseline land cover map reclassified into IPCC classes
    landcover_bl_remapped = landcover \
        .select(f'y{lc_year_start}') \
        .remap(pm.translation_matrix[0], pm.translation_matrix[1])
    
    # target land cover map reclassified into IPCC classes
    landcover_tg_remapped = landcover \
            .select(f'y{lc_year_end}') \
            .remap(pm.translation_matrix[0],pm.translation_matrix[1])
    
    landcover_end = landcover \
            .select(f'y{lc_year_end}') \
            .rename('landcover_end')
    water_mask = landcover_end \
            .where(landcover_end.eq(210), 0) \
            .rename('water')


    # compute transition map (first digit for baseline land cover, and second digit for target year land cover)
    landcover_transition = landcover_bl_remapped \
            .multiply(10) \
            .add(landcover_tg_remapped)

    # definition of land cover transitions as degradation (-1), improvement (1), or no relevant change (0)
    trans_matrix_flatten = [item for sublist in model.transition_matrix for item in sublist]
    landcover_degredation = landcover_transition \
            .remap(pm.IPCC_lc_change_matrix, trans_matrix_flatten)
    
    # use the byte convention 
    # 1 degraded - 2 stable - 3 improved
    landcover_degredation = landcover_degredation \
        .remap([1,0,-1,pm.int_16_min],[3,2,1,0]) \
        .uint8() \
        .rename("degradation")

    return landcover_degredation.addBands(water_mask.uint8())
