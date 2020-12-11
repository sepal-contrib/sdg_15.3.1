import ee 

from scripts import parameter as pm

ee.Initialize()

def land_cover(io, aoi_io, output):
    """Calculate land cover indicator"""

    ## load the land cover map
    lc = ee.Image(pm.land_cover)
    lc = lc \
        .where(lc.eq(9999), -32768) \
        .updateMask(lc.neq(-32768))

    # Remap LC according to input matrix
    lc_remapped = lc \
        .select(f'y{io.start}') \
        .remap(io.transition_matrix[0], io.transition_matrix[1])
    
    for year in range(io.start + 1, io.end + 1):
        lc_remapped = lc_remapped \
            .addBands(lc.select(f'y{year}')) \
            .remap(io.transition_matrix[0], io.transition_matrix[1])

    ## target land cover map reclassified to IPCC 6 classes
    lc_bl = lc_remapped.select(0)

    ## baseline land cover map reclassified to IPCC 6 classes
    lc_tg = lc_remapped.select(len(lc_remapped.getInfo()['bands']) - 1)

    ## compute transition map (first digit for baseline land cover, and second digit for target year land cover)
    lc_tr = lc_bl.multiply(10).add(lc_tg)

    ## definition of land cover transitions as degradation (-1), improvement (1), or no relevant change (0)
    
    lc_dg = lc_tr.remap(pm.IPCC_matrix,io.transition_matrix)

    ## Remap persistence classes so they are sequential. This
    ## makes it easier to assign a clear color ramp in QGIS.
    
    sequential_matrix = [
        1, 12, 13, 14, 15, 16, 17,
        21, 2, 23, 24, 25, 26, 27,
        31, 32, 3, 34, 35, 36, 37,
        41, 42, 43, 4, 45, 46, 47,
        51, 52, 53, 54, 5, 56, 57,
        61, 62, 63, 64, 65, 6, 67,
        71, 72, 73, 74, 75, 76, 7
    ]
    
    lc_tr = lc_tr.remap(pm.IPCC_matrix, sequential_matrix)

    out = ee.Image(
        lc_dg \
        .addBands(lc.select(f'y{io.start}')) \
        .addBands(lc.select(f'y{io.target_start}')) \
        .addBands(lc_tr)
    )

    # Return the full land cover timeseries so it is available for reporting
    out.addBands(lc_remapped)

    out= out.unmask(-32768).int16()

    return out