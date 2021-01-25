import ee 

from component import parameter as pm

ee.Initialize()

def land_cover(io, aoi_io, output):
    """Calculate land cover indicator"""

    ## load the land cover map
    lc = ee.Image(pm.land_cover).clip(aoi_io.get_aoi_ee().geometry().bounds())
    lc = lc \
        .where(lc.eq(9999), pm.int_16_min) \
        .updateMask(lc.neq(pm.int_16_min))

    # Remap LC according to input matrix, aggregation of land cover classesclasses to IPCC classes.
    #TODO:custom aggregation based on user inputs
    lc_remapped = lc \
        .select(f'y{io.start}') \
        .remap(pm.translation_matrix[0], pm.translation_matrix[1])
    
    for year in range(io.start + 1, io.end):
        lc_remapped = lc_remapped \
            .addBands(lc.select(f'y{year}')) \
            .remap(pm.translation_matrix[0],pm.translation_matrix[1])

    ## target land cover map reclassified to IPCC 6 classes
    lc_bl = lc_remapped.select(0)

    ## baseline land cover map reclassified to IPCC 6 classes
    lc_tg = lc_remapped.select(len(lc_remapped.getInfo()['bands']) - 1)

    ## compute transition map (first digit for baseline land cover, and second digit for target year land cover)
    lc_tr = lc_bl \
            .multiply(10) \
            .add(lc_tg)

    ## definition of land cover transitions as degradation (-1), improvement (1), or no relevant change (0)
    trans_matrix_flatten = [item for sublist in io.transition_matrix for item in sublist]
    lc_dg = lc_tr \
            .remap(pm.IPCC_lc_change_matrix, trans_matrix_flatten) \
            .rename("degredation")

    ## Remap persistence classes so they are sequential.
    lc_tr = lc_tr.remap(pm.IPCC_lc_change_matrix, pm.sequential_matrix)

    out = ee.Image(
        lc_dg \
        .addBands(lc.select(f'y{io.start}')) \
        .addBands(lc.select(f'y{io.target_start}')) \
        .addBands(lc_tr)
    )

    # Return the full land cover timeseries so it is available for reporting
    out.addBands(lc_remapped)

    out= out.unmask(pm.int_16_min).int16()

    return out