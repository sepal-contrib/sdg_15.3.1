import ee 
from functools import partial

from scripts import utils as u
from scripts import parameter as pm
from scripts import productivity as prod

ee.Initialize()


def soil_organic_carbon(io, aoi_io, output):
    """Calculate soil organic carbon indicator"""
    
    #Inputs: start_year, end_year, conversion_coef
    
    soc = ee.Image(pm.soc)
    soc = soc.updateMask(soc.neq(-32767))
    
    lc = ee.Image(pm.land_cover) \
        .select(ee.List.sequence(io.start - 1993, io.end -1993, 1))
    
    lc = lc \
        .where(lc.eq(9999), -32768) \
        .updateMask(lc.neq(-32768))
    
    if not io.conversion_coef:
        ipcc_climate_zones = ee.Image(pm.ipcc_climate_zones)
        climate_conversion_coef = ipcc_climate_zones.remap(pm.climate_conversion_matrix[0], pm.climate_conversion_matrix[1])
    else: 
        climate_conversion_coef = io.conversion_coef 
        
        
    #Cumpute the soc change for the first two years
    lc_time0 = lc \
            .select(0) \
            .remap(pm.translation_matrix[0],pm.translation_matrix[1])
        
    lc_time1 = lc \
            .select(1) \
            .remap(pm.translation_matrix[0],pm.translation_matrix[1])
    
     # compute transition map for the first two years(1st digit for baseline land cover, 2nd for target land cover)
    lc_transition = lc_time0 \
                .multiply(10) \
                .add(lc_time1)
            
    # compute raster to registrar years since transition for the first and second year
    lc_transition_time =ee.Image(2).where(lc_time0.neq(lc_time1),1)
    
    #stock change factor for land use
    #333 and -333 will be recoded using the choosen climate coef.
    
    lc_transition_climate_coef_tmp =  lc_transition \
            .remap(pm.IPCC_lc_change_matrix, pm.c_conversion_factor)
    lc_transition_climate_coef = lc_transition_climate_coef_tmp \
            .where(lc_transition_climate_coef_tmp.eq(333),climate_conversion_coef) \
            .where(lc_transition_climate_coef_tmp.eq(-333), ee.Image(1).divide(climate_conversion_coef))
                            
    #stock change factor for management regime
    lc_transition_management_factor = lc_transition.remap(pm.IPCC_lc_change_matrix, pm.management_factor)
    #Stock change factor for input of organic matter
    lc_transition_organic_factor = lc_transition.remap(pm.IPCC_lc_change_matrix, pm.input_factor)
    
    organic_carbon_change = soc \
                .subtract(soc \
                    .multiply(lc_transition_climate_coef) \
                    .multiply(lc_transition_management_factor) \
                    .multiply(lc_transition_organic_factor)
                 ) \
                 .divide(20)
            
    #compute final soc for the period
    soc_time1 = soc.subtract(organic_carbon_change)
            
            #add to land cover and soc to stacks from both dates for the first period
    lc_images = ee.Image(lc_time0) \
                .addBands(lc_time1)
            
    soc_images = ee.Image(soc) \
                .addBands(soc_time1)
    
    #Cumpute the soc change for the rest of  the years
    
    for year_index in range(1, io.end - io.start):
        lc_time0 = lc \
            .select(year_index) \
            .remap(pm.translation_matrix[0],pm.translation_matrix[1])
        
        lc_time1 = lc \
            .select(year_index +1) \
            .remap(pm.translation_matrix[0],pm.translation_matrix[1])
        
        lc_transition_time = lc_transition_time \
            .where(lc_time0.eq(lc_time1),lc_transition_time.add(ee.Image(1))) \
            .where(lc_time0.neq(lc_time1),ee.Image(1))
                
        #compute transition map (1st digit for baseline land cover, 2nd for target land cover)
        #But only update where changes acually occured.
        lc_transition_temp = lc_time0.multiply(10).add(lc_time1)
        lc_transition =lc_transition.where(lc_time0.neq(lc_time1), lc_transition_temp)
        
        #stock change factor for land use
        #333 and -333 will be recoded using the choosen climate coef.            
        lc_transition_climate_coef_tmp =  lc_transition \
            .remap(pm.IPCC_lc_change_matrix, pm.c_conversion_factor)
        lc_transition_climate_coef = lc_transition_climate_coef_tmp \
            .where(lc_transition_climate_coef_tmp.eq(333),climate_conversion_coef) \
            .where(lc_transition_climate_coef_tmp.eq(-333), ee.Image(1).divide(climate_conversion_coef))
                            
        #stock change factor for management regime
        lc_transition_management_factor = lc_transition.remap(pm.IPCC_lc_change_matrix, pm.management_factor)
        #Stock change factor for input of organic matter
        lc_transition_organic_factor = lc_transition.remap(pm.IPCC_lc_change_matrix, pm.input_factor)
            
        organic_carbon_change = organic_carbon_change \
            .where(
                    lc_time0.neq(lc_time1),
                    soc_images \
                        .select(year_index) \
                        .subtract(soc_images \
                                  .select(year_index) \
                                  .multiply(lc_transition_climate_coef) \
                                  .multiply(lc_transition_management_factor) \
                                  .multiply(lc_transition_organic_factor)
                                  ).divide(20)) \
            .where(lc_transition_time.gt(20),0)
            
            
        soc_final = soc_images \
            .select(year_index) \
            .subtract(organic_carbon_change)
                        
        lc_images = lc_images \
            .addBands(lc_time1)
            
        soc_images = soc_images \
            .addBands(soc_final)
            
    #Compute soc percent change for the analsis period
    soc_percent_change = soc_images \
        .select(io.end - io.start) \
        .subtract(soc_images.select(0)) \
        .divide(soc_images.select(0)) \
        .multiply(100)
    
    soc_class = ee.Image(-32768) \
        .where(soc_percent_change.gt(10),1) \
        .where(soc_percent_change.lt(10).And(soc_percent_change.gt(-10)),0) \
        .where(soc_percent_change.lt(-10),-1)\
        .rename('soc_class')

    output = soc_class.unmask(-32768).int16()
    
    return output
    
def land_cover(io, aoi_io, output):
    """Calculate land cover indicator"""

    ## load the land cover map
    lc = ee.Image(pm.land_cover)
    lc = lc \
        .where(lc.eq(9999), -32768) \
        .updateMask(lc.neq(-32768))

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

    out= out.unmask(-32768).int16()

    return out

def integrate_ndvi_climate(aoi_io, io, output):
    
    # create the composite image collection
    i_img_coll = ee.ImageCollection([])
    
    for sensor in io.sensors:
        # get the imagecollection 
        sat = ee.ImageCollection(pm.sensors[sensor])
        # rename the bands 
        sat = sat.map(partial(u.rename_band, sensor=sensor))
        # mask the clouds 
        sat = sat.map(partial(u.cloud_mask, sensor=sensor))
    
        i_img_coll = i_img_coll.merge(sat)
    
    # Filtering the img collection  using start year and end year and filtering to the bb area of interest
    i_img_coll = i_img_coll.filterDate(f'{io.start}-01-01', f'{io.end}-12-31').filterBounds(aoi_io.get_aoi_ee())

    # Function to integrate observed NDVI datasets at the annual level
    ndvi_coll = i_img_coll.map(prod.CalcNDVI)
    
    ndvi_int = prod.int_yearly_ndvi(ndvi_coll, io.start, io.end)

    # get the trends
    #trend = ndvi_trend(io.start, io.end, ndvi_int)

    # process the climate dataset to use with the pixel restrend, RUE calculation
    precipitation = ee.ImageCollection(pm.precipitation) \
        .filterDate(f'{io.start}-01-01',f'{io.end}-12-31') \
        .select('precipitation')
    
    climate_int = prod.int_yearly_climate(precipitation, io.start, io.end)
    
    return (ndvi_int, climate_int)

def productivity_trajectory(io, nvdi_yearly_integration, climate_yearly_integration, output):
    """Productivity Trend describes the trajectory of change in productivity over time. Trend is calculated by fitting a robust, non-parametric linear regression model.The significance of trajectory slopes at the P <= 0.05 level should be reported in terms of three classes:
        1) Z score < -1.96 = Potential degradation, as indicated by a significant decreasing trend,
        2) Z score > 1.96 = Potential improvement, as indicated by a significant increasing trend, or
        3) Z score > -1.96 AND < 1.96 = No significant change

In order to correct the effects of climate on productivity, climate adjusted trend analysis can be performed. There such methods are coded for the trajectory analysis. 

The following code runs the selected trend method and produce an output by reclassifying the trajecry slopes. 
    """
    
    #trajectories = ['ndvi_trend', 'p_restrend', 's_restrend', 'ue_trend']

    # Run the selected algorithm
    # nvi trend
    if io.trajectory == pm.trajectories[0]:
        lf_trend, mk_trend = prod.ndvi_trend(io.start, io.end, nvdi_yearly_integration)
    # p restrend
    elif io.trajectory == pm.trajectories[1]:
        lf_trend, mk_trend = prod.p_restrend(io.start, io.end, nvdi_yearly_integration, climate_yearly_integration)
    # s restrend
    elif io.trajectory == pm.trajectories[2]:
        #TODO: need to code this
        raise NameError("s_restrend method not yet supported")
    # ue trend
    elif io.trajectory == pm.trajectories[3]:
        lf_trend, mk_trend = prod.ue_trend(io.start, io.end, nvdi_yearly_integration, climate_yearly_integration)
    else:
        raise NameError(f'Unrecognized method "{io.trajectory}"')

    # Define Kendall parameter values for a significance of 0.05
    period = io.end - io.start + 1
    kendall90 = pm.get_kendall_coef(period, 90)
    kendall95 = pm.get_kendall_coef(period, 95)
    kendall99 = pm.get_kendall_coef(period, 99)

    # Create final productivity trajectory output layer. Positive values are 
    # significant increase, negative values are significant decrease.
    signif = ee.Image(-32768) \
        .where(lf_trend.select('scale').gt(0).And(mk_trend.abs().gte(kendall90)), 1) \
        .where(lf_trend.select('scale').gt(0).And(mk_trend.abs().gte(kendall95)), 2) \
        .where(lf_trend.select('scale').gt(0).And(mk_trend.abs().gte(kendall99)), 3) \
        .where(lf_trend.select('scale').lt(0).And(mk_trend.abs().gte(kendall90)), -1) \
        .where(lf_trend.select('scale').lt(0).And(mk_trend.abs().gte(kendall95)), -2) \
        .where(lf_trend.select('scale').lt(0).And(mk_trend.abs().gte(kendall99)), -3) \
        .where(mk_trend.abs().lte(kendall90), 0) \
        .where(lf_trend.select('scale').abs().lte(10), 0).rename('signif')

    trajectory_class = ee.Image(-32768) \
        .where(signif.gt(0),1) \
        .where(signif.eq(0),0) \
        .where(signif.lt(0).And(signif.neq(-32768)),-1) \
        .rename('trajectory_class')

    output = ee.Image(
        trajectory_class \
        .addBands(lf_trend.select('scale')) \
        .addBands(signif) \
        .addBands(mk_trend) \
        .unmask(-32768) \
        .int16()
    )
    
    return output

def productivity_performance(io_aoi, io, nvdi_yearly_integration, climate_yearly_integration, output):
    """It measures local productivity relative to other similar vegetation types in similar land cover types and bioclimatic regions. It indicates how a region is performing relative to other regions with similar productivity potential.
        Steps:
        *Computation of mean NDVI for the analysis period,
        *Creation of ecologically similar regions based on USDA taxonomy and ESA CCI land cover data sets.
        *Extraction of mean NDVI for each region, creation of  a frequency distribution of this data to determine the value that represents 90th percentile,
        *Computation of the ratio of mean NDVI and max productivity (90th percentile)

    """

    #nvdi_yearly_integration = ee.Image(nvdi_yearly_integration)

    # land cover data from esa cci
    lc = ee.Image(pm.land_cover)
    lc = lc \
        .where(lc.eq(9999), -32768) \
        .updateMask(lc.neq(-32768))

    # global agroecological zones from IIASA
    soil_tax_usda = ee.Image(pm.soil_tax)

    ###############################################
    # why clipping twice ??
    
    # Make sure the bounding box of the poly is used, and not the geodesic 
    # version, for the clipping
    poly = io_aoi.get_aoi_ee().geometry()
    #############################################

    # compute mean ndvi for the period
    
    ndvi_mean = nvdi_yearly_integration \
        .select('ndvi') \
        .reduce(ee.Reducer.mean()) \
        .rename(['ndvi'])

    ################################
    
    # should not be here it's a hidden parameter
    
    # Handle case of year_start that isn't included in the CCI data
    lc_year_start = min(max(io.start, pm.lc_first_year), pm.lc_last_year)
    
    #################################
    
    # reclassify lc to ipcc classes
    lc_reclass = lc \
        .select(f'y{lc_year_start}') \
        .remap(pm.ESA_lc_classes, pm.reclassification_matrix)

    # create a binary mask.
    mask = ndvi_mean.neq(0)

    # define projection attributes
    #TODO: reprojection does not work for a collection that has default projection WGS84(crs:4326). Need to find a solution to get the scale information from input sensors.
    # define unit of analysis as the intersect of soil_tax_usda and land cover
    similar_ecoregions = soil_tax_usda.multiply(100).add(lc_reclass)

    # create a 2 band raster to compute 90th percentile per ecoregion (analysis restricted by mask and study area)
    ndvi_id = ndvi_mean.addBands(similar_ecoregions).updateMask(mask)

    # compute 90th percentile by unit
    percentile_90 = ndvi_id.reduceRegion(
        reducer=ee.Reducer.percentile([90]).group(
            groupField=1, 
            groupName='code'
        ),
        geometry=poly,
        scale=30,
        maxPixels=1e15
    )

    # Extract the cluster IDs and the 90th percentile
    groups = ee.List(percentile_90.get("groups"))
    ids = groups.map(lambda d: ee.Dictionary(d).get('code'))
    percentile = groups.map(lambda d: ee.Dictionary(d).get('p90'))

    # remap the similar ecoregion raster using their 90th percentile value
    ecoregion_perc90 = similar_ecoregions.remap(ids, percentile)

    # compute the ratio of observed ndvi to 90th for that class
    observed_ratio = ndvi_mean.divide(ecoregion_perc90)

    # create final degradation output layer (9999 is background), 0 is not
    # degreaded, -1 is degraded
    prod_performance_class = ee.Image(-32768) \
        .where(observed_ratio.gte(0.5), 0) \
        .where(observed_ratio.lte(0.5), -1) \
        .rename('performance_class')

    output = ee.Image(
        prod_performance_class.addBands(observed_ratio.multiply(10000)) \
        .addBands(similar_ecoregions) \
        .unmask(-32768) \
        .int16()
    )
    
    return output

def productivity_state(aoi_io, io, ndvi_yearly_integration, climate_int, output):
    """It represents the level of relative roductivity in a pixel compred to a historical observations of productivity for that pixel. For more, see Ivits, E., & Cherlet, M. (2016). Land productivity dynamics: towards integrated assessment of land degradation at global scales. In. Luxembourg: Joint Research Centr, https://publications.jrc.ec.europa.eu/repository/bitstream/JRC80541/lb-na-26052-en-n%20.pdf
        It alows for the detection of recent changes in primary productivity as compared to the baseline period.
        Steps:
        *Definition of baselene and reporting perod,
        *Computation of frequency distribution of mean NDVI for baseline period with addition of 5% at the both extremes of the distribution to alow inclusion of some, if an, missed extreme values in NDVI.
        *Creation of 10 percentile classess using the data from the frequency distribution.
        *computation of mean NDVI for baseline period, and determination of the percentile class it belongs to. Assignmentof the mean NDVI for the base line period the number corresponding to that percentile class. 
        *computation of mean NDVI for reporting period, and determination of the percentile class it belongs to. Assignmentof the mean NDVI for the reporting period the number corresponding to that percentile class. 
        *Determination of the difference in class number between the reporting and baseline period,
        *
    """    
    
    # compute min and max of annual ndvi for the baseline period
    baseline_filter = ee.Filter.rangeContains('year', io.start, io.target_start)
    target_filter =ee.Filter.rangeContains('year', io.target_start, io.end)
    
    baseline_ndvi_range = ndvi_yearly_integration \
        .filter(baseline_filter) \
        .select('ndvi') \
        .reduce(ee.Reducer.percentile([0, 100]))

    #convert baseline ndvi imagecollection to bands
    baseline_ndvi_collection = ndvi_yearly_integration \
        .filter(baseline_filter) \
        .select('ndvi')

    baseline_ndvi_images = ee.ImageCollection.toBands(baseline_ndvi_collection)

    # add two bands to the time series: one 5% lower than min and one 5% higher than max
    
    ##############################
    
    # this var needs to have an explicit name
    baseline_ndvi_5p = (baseline_ndvi_range.select('ndvi_p100').subtract(baseline_ndvi_range.select('ndvi_p0'))).multiply(0.05)
    
    #############################
    
    baseline_ndvi_extended = baseline_ndvi_images \
        .addBands(
            baseline_ndvi_range \
            .select('ndvi_p0') \
            .subtract(baseline_ndvi_5p)
        ) \
        .addBands(
            baseline_ndvi_range \
            .select('ndvi_p100') \
            .add(baseline_ndvi_5p)
        )

    # compute percentiles of annual ndvi for the extended baseline period
    percentiles = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    baseline_ndvi_perc = baseline_ndvi_extended.reduce(ee.Reducer.percentile(percentiles))

    # compute mean ndvi for the baseline and target period period
    baseline_ndvi_mean = ndvi_yearly_integration \
        .filter(baseline_filter) \
        .select('ndvi') \
        .reduce(ee.Reducer.mean()) \
        .rename(['ndvi'])
    
    target_ndvi_mean = ndvi_yearly_integration \
        .filter(target_filter) \
        .select('ndvi') \
        .reduce(ee.Reducer.mean()) \
        .rename(['ndvi'])

    # reclassify mean ndvi for baseline period based on the percentiles
    baseline_classes = ee.Image(-32768) \
        .where(baseline_ndvi_mean.lte(baseline_ndvi_perc.select('p10')), 1) \
        .where(baseline_ndvi_mean.gt(baseline_ndvi_perc.select('p10')), 2) \
        .where(baseline_ndvi_mean.gt(baseline_ndvi_perc.select('p20')), 3) \
        .where(baseline_ndvi_mean.gt(baseline_ndvi_perc.select('p30')), 4) \
        .where(baseline_ndvi_mean.gt(baseline_ndvi_perc.select('p40')), 5) \
        .where(baseline_ndvi_mean.gt(baseline_ndvi_perc.select('p50')), 6) \
        .where(baseline_ndvi_mean.gt(baseline_ndvi_perc.select('p60')), 7) \
        .where(baseline_ndvi_mean.gt(baseline_ndvi_perc.select('p70')), 8) \
        .where(baseline_ndvi_mean.gt(baseline_ndvi_perc.select('p80')), 9) \
        .where(baseline_ndvi_mean.gt(baseline_ndvi_perc.select('p90')), 10)

    # reclassify mean ndvi for target period based on the percentiles
    target_classes = ee.Image(-32768) \
        .where(target_ndvi_mean.lte(baseline_ndvi_perc.select('p10')), 1) \
        .where(target_ndvi_mean.gt(baseline_ndvi_perc.select('p10')), 2) \
        .where(target_ndvi_mean.gt(baseline_ndvi_perc.select('p20')), 3) \
        .where(target_ndvi_mean.gt(baseline_ndvi_perc.select('p30')), 4) \
        .where(target_ndvi_mean.gt(baseline_ndvi_perc.select('p40')), 5) \
        .where(target_ndvi_mean.gt(baseline_ndvi_perc.select('p50')), 6) \
        .where(target_ndvi_mean.gt(baseline_ndvi_perc.select('p60')), 7) \
        .where(target_ndvi_mean.gt(baseline_ndvi_perc.select('p70')), 8) \
        .where(target_ndvi_mean.gt(baseline_ndvi_perc.select('p80')), 9) \
        .where(target_ndvi_mean.gt(baseline_ndvi_perc.select('p90')), 10)

    # difference between start and end clusters >= 2 means improvement (<= -2 
    # is degradation)
    classes_change = target_classes \
            .subtract(baseline_classes) \
            .where(baseline_ndvi_mean \
                .subtract(target_ndvi_mean) \
                .abs().lte(100) \
            , 0)
    #reclassification to get the degredation classes
    degredation_classes = ee.Image(-32768) \
        .where(classes_change.gte(2),1) \
        .where(classes_change.lte(-2).And(classes_change.neq(-32768)),-1) \
        .where(classes_change.lt(2).And(classes_change.gt(-2)),0) \
        .rename("state_class")

    output = ee.Image(
        degredation_classes \
        .addBands(classes_change) \
        .addBands(baseline_classes) \
        .addBands(target_classes) \
        .addBands(baseline_ndvi_mean) \
        .addBands(target_ndvi_mean) \
        .unmask(-32768) \
        .int16()
    )

   
    return output

def productivity_final(trajectory, performance, state, output):
    trajectory_class = trajectory.select('trajectory_class')
    performance_class = performance.select('performance_class')
    state_class = state.select('state_class')

    productivity = ee.Image(-32768)\
            .where(trajectory_class.eq(1).And(state_class.eq(1)).And(performance_class.eq(0)),1) \
            .where(trajectory_class.eq(1).And(state_class.eq(1)).And(performance_class.eq(-1)),1) \
            .where(trajectory_class.eq(1).And(state_class.eq(0)).And(performance_class.eq(0)),1) \
            .where(trajectory_class.eq(1).And(state_class.eq(0)).And(performance_class.eq(-1)),1) \
            .where(trajectory_class.eq(1).And(state_class.eq(-1)).And(performance_class.eq(0)),1) \
            .where(trajectory_class.eq(1).And(state_class.eq(-1)).And(performance_class.eq(-1)),-1) \
            .where(trajectory_class.eq(0).And(state_class.eq(1)).And(performance_class.eq(0)),0) \
            .where(trajectory_class.eq(0).And(state_class.eq(1)).And(performance_class.eq(-1)),0) \
            .where(trajectory_class.eq(0).And(state_class.eq(0)).And(performance_class.eq(0)),0) \
            .where(trajectory_class.eq(0).And(state_class.eq(0)).And(performance_class.eq(-1)),-1) \
            .where(trajectory_class.eq(0).And(state_class.eq(-1)).And(performance_class.eq(0)),-1) \
            .where(trajectory_class.eq(0).And(state_class.eq(-1)).And(performance_class.eq(-1)),-1)\
            .where(trajectory_class.eq(-1).And(state_class.eq(1)).And(performance_class.eq(0)),-1) \
            .where(trajectory_class.eq(-1).And(state_class.eq(1)).And(performance_class.eq(-1)),-1) \
            .where(trajectory_class.eq(-1).And(state_class.eq(0)).And(performance_class.eq(0)),-1) \
            .where(trajectory_class.eq(-1).And(state_class.eq(0)).And(performance_class.eq(-1)),-1) \
            .where(trajectory_class.eq(-1).And(state_class.eq(-1)).And(performance_class.eq(0)),-1) \
            .where(trajectory_class.eq(-1).And(state_class.eq(-1)).And(performance_class.eq(-1)),-1)
    
    output = productivity \
            .unmask(-32768) \
            .int16()
    return output
def indicator_15_3_1(productivity, landcover,soc, output):
    indicator = ee.Image(-32768) \
            .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(1)),1) \
            .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(0)),1) \
            .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(-1)),-1) \
            .where(productivity.eq(1).And(landcover.eq(0)).And(soc.eq(1)),1) \
            .where(productivity.eq(1).And(landcover.eq(0)).And(soc.eq(0)),1) \
            .where(productivity.eq(1).And(landcover.eq(0)).And(soc.eq(-1)),-1) \
            .where(productivity.eq(1).And(landcover.eq(-1)).And(soc.eq(1)),-1) \
            .where(productivity.eq(1).And(landcover.eq(-1)).And(soc.eq(0)),-1) \
            .where(productivity.eq(1).And(landcover.eq(-1)).And(soc.eq(-1)),-1) \
            .where(productivity.eq(0).And(landcover.eq(1)).And(soc.eq(1)),1) \
            .where(productivity.eq(0).And(landcover.eq(1)).And(soc.eq(0)),1) \
            .where(productivity.eq(0).And(landcover.eq(1)).And(soc.eq(-1)),-1) \
            .where(productivity.eq(0).And(landcover.eq(0)).And(soc.eq(1)),1) \
            .where(productivity.eq(0).And(landcover.eq(0)).And(soc.eq(0)),0) \
            .where(productivity.eq(0).And(landcover.eq(0)).And(soc.eq(-1)),-1) \
            .where(productivity.eq(0).And(landcover.eq(-1)).And(soc.eq(1)),-1) \
            .where(productivity.eq(0).And(landcover.eq(-1)).And(soc.eq(0)),-1) \
            .where(productivity.eq(0).And(landcover.eq(-1)).And(soc.eq(-1)),-1) \
            .where(productivity.eq(-1).And(landcover.eq(1)).And(soc.eq(1)),-1) \
            .where(productivity.eq(-1).And(landcover.eq(1)).And(soc.eq(0)),-1) \
            .where(productivity.eq(-1).And(landcover.eq(1)).And(soc.eq(-1)),-1) \
            .where(productivity.eq(-1).And(landcover.eq(0)).And(soc.eq(1)),-1) \
            .where(productivity.eq(-1).And(landcover.eq(0)).And(soc.eq(0)),-1) \
            .where(productivity.eq(-1).And(landcover.eq(0)).And(soc.eq(-1)),-1) \
            .where(productivity.eq(-1).And(landcover.eq(-1)).And(soc.eq(1)),-1) \
            .where(productivity.eq(-1).And(landcover.eq(-1)).And(soc.eq(0)),-1) \
            .where(productivity.eq(-1).And(landcover.eq(-1)).And(soc.eq(-1)),-1) 
    output = indicator \
            .unmask(-32768) \
            .int16()
    return output

