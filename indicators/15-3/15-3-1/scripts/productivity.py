from functools import partial

import ee

import parameter as pm
import utils as u

ee.Initialize()

#year_start = 2015
#year_end = 2020

def compute_productivity(aoi_io, io, output):
    
    # create the composite image collection
    i_img_coll = ee.ImageCollection([])
    for sensor in io.sensors:
        
        # get the featureCollection 
        sat = ee.FeatureCollection(pm.sensors[sensor])
        # rename the bands 
        sat = sat.map(partial(u.rename_band, sensor=sensor))
        # mask the clouds 
        sat = sat.map(partial(u.cloud_mask, sensor=sensor))
    
        i_img_coll = i_img_coll.merge(sat)
    
    # Filtering the img collection  using start year and end year and filtering to the bb area of interest
    i_img_coll = i_img_coll.filterDate(io.start, io.end).filterBounds(aoi_io.get_aoi_ee())

    # Function to integrate observed NDVI datasets at the annual level
    ndvi_coll = i_img_coll.map(u.CalcNDVI)
    
    ndvi_int = u.int_yearly_ndvi(ndvi_coll)

    # get the trends
    trend = ndvi_trend(year_start, year_end, ndvi_int)

    # process the climate dataset to use with the pixel restrend, RUE calculation
    precipitation = ee.ImageCollection(pm.precipitation) \
        .filterDate(io.start,io.end) \
        .select('precipitation')
    
    climate_int = u.int_yearly_climate(precipitation)
    
    ##########################
    ##      p_restrend      ##
    ##########################
    
    ## Apply function to create image collection of ndvi and climate
    ndvi_1yr_coll = f_img_coll(ndvi_int)

    ## Compute linear trend function to predict ndvi based on climate (independent are followed by dependent var
    lf_clim_ndvi = ndvi_1yr_coll \
        .select(['clim', 'ndvi']) \
        .reduce(ee.Reducer.linearFit())

    ## Apply function to  predict NDVI based on climate
    ndvi_1yr_p = ee.ImageCollection(ee.List(
        ndvi_1yr_coll \
        .select('clim') \
        .iterate(partial(u.f_ndvi_clim_p, lf_clim_ndvi = lf_clim_ndvi), first)
    ))

    ## Apply function to compute NDVI annual residuals
    ndvi_1yr_r = f_ndvi_clim_r_coll(io.start, io.end, ndvi_1yr_coll, ndvi_1yr_p)

    ## Fit a linear regression to the NDVI residuals
    p_lf_trend = ndvi_1yr_r.select(['year', 'ndvi_res']).reduce(ee.Reducer.linearFit())

    ## Compute Kendall statistics
    p_mk_trend = u.mann_kendall(ndvi_1yr_r.select('ndvi_res'))


    ########################
    ##      ue_trend      ##
    ########################

    # Convert the climate layer to meters (for precip) so that RUE layer can be
    # scaled correctly
    # TODO: Need to handle scaling for ET for WUE
    
    # Apply function to compute ue and store as a collection
    ue_1yr_coll = u.f_img_coll(start, end, ndvi_int, climate_int)

    # Compute linear trend function to predict ndvi based on year (ndvi trend)
    ue_lf_trend = ue_1yr_coll.select(['year', 'ue']).reduce(ee.Reducer.linearFit())

    # Compute Kendall statistics
    mk_trend = u.mann_kendall(ue_1yr_coll.select('ue'))



def productivity_trajectory(year_start, year_end, method, ndvi_1yr,
                            climate_1yr):
    #logger.debug("Entering productivity_trajectory function.")

    #climate_1yr = climate_1yr.where(climate_1yr.eq(9999), -32768)
    #climate_1yr = climate_1yr.updateMask(climate_1yr.neq(-32768))

    #if climate_gee_dataset == None and method != 'ndvi_trend':
       # raise Error("Must specify a climate dataset")

    #ndvi_dataset = ee.Image(ndvi_gee_dataset)
    #ndvi_dataset = ndvi_dataset.where(ndvi_dataset.eq(9999), -32768)
    #ndvi_dataset = ndvi_dataset.updateMask(ndvi_dataset.neq(-32768))

    #ndvi_mean = ndvi_1yr.select(ee.List(['y{}'.format(i) for i in range(year_start, year_end + 1)])).reduce(ee.Reducer.mean()).rename(['ndvi'])

    # Run the selected algorithm
    if method == 'ndvi_trend':
        lf_trend, mk_trend = ndvi_trend(year_start, year_end, ndvi_1yr)
    elif method == 'p_restrend':
        lf_trend, mk_trend = p_restrend(year_start, year_end, ndvi_1yr, climate_1yr)
        if climate_1yr == None:
            climate_1yr = precp_gpcc
    elif method == 's_restrend':
        #TODO: need to code this
        raise NameError("s_restrend method not yet supported")
    elif method == 'ue':
        lf_trend, mk_trend = ue_trend(year_start, year_end, ndvi_1yr, climate_1yr)
    else:
        raise NameError("Unrecognized method '{}'".format(method))

    # Define Kendall parameter values for a significance of 0.05
    period = year_end - year_start + 1
    kendall90 = get_kendall_coef(period, 90)
    kendall95 = get_kendall_coef(period, 95)
    kendall99 = get_kendall_coef(period, 99)

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

    return ee.Image(lf_trend.select('scale').addBands(signif).addBands(mk_trend).unmask(-32768).int16())

ue_trend_re = ue_trend(year_start, year_end, ndvi_int, climate_1yr)
print(ue_trend_re[1].getInfo())

productivity_traj_layer = productivity_trajectory(year_start, year_end, 'ue', ndvi_int, climate_1yr)
print(productivity_traj_layer.getInfo())

productivity_traj_layer = productivity_traj_layer.clip(AOI)

print(productivity_traj_layer.getInfo()["bands"])

Map = emap.Map(center=(21.21,92.16), zoom=10)
Map.addLayer(productivity_traj_layer.select('signif'),{"max": 3, "min":-3,"palette":["#762a83","#af8dc3","#e7d4e8","#f7f7f7","#d9f0d3","#7fbf7b","#1b7837"]}, 'productivity_traj_layer')
plot =ee.FeatureCollection("users/amitghosh/plantationInOutCampFAOv1")
Map.addLayer(plot,{},'plot', shown=True, opacity=0.4)
Map.addLayerControl()
Map

ee.batch.Export.image.toDrive(productivity_traj_layer,
    description="Cox_s bazar trajectory",
    fileNamePrefix="degradation",
    region=AOI,
    scale=10,
    maxPixels=1e13,
).start()

task = ee.batch.Task.list()[0]
task.status()

def productivity_performance(year_start, year_end, ndvi_1yr, AOI):

    ndvi_1yr = ee.Image(ndvi_1yr)


    # land cover data from esa cci
    lc = ee.Image("users/geflanddegradation/toolbox_datasets/lcov_esacc_1992_2018")
    lc = lc.where(lc.eq(9999), -32768)
    lc = lc.updateMask(lc.neq(-32768))

    # global agroecological zones from IIASA
    soil_tax_usda = ee.Image("users/geflanddegradation/toolbox_datasets/soil_tax_usda_sgrid")

    # Make sure the bounding box of the poly is used, and not the geodesic 
    # version, for the clipping
    poly = ee.Geometry(AOI, opt_geodesic=False)

    # compute mean ndvi for the period
    ndvi_avg = ndvi_1yr.select(ee.List(['y{}'.format(i) for i in range(year_start, year_end + 1)])) \
        .reduce(ee.Reducer.mean()).rename(['ndvi']).clip(poly)

    # Handle case of year_start that isn't included in the CCI data
    if year_start > 2015:
        lc_year_start = 2015
    elif year_start < 1992:
        lc_year_start = 1992
    else:
        lc_year_start = year_start
    # reclassify lc to ipcc classes
    lc_t0 = lc.select('y{}'.format(lc_year_start)) \
        .remap([10, 11, 12, 20, 30, 40, 50, 60, 61, 62, 70, 71, 72, 80, 81, 82, 90, 100, 160, 170, 110, 130, 180, 190, 120, 121, 122, 140, 150, 151, 152, 153, 200, 201, 202, 210], 
               [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36])

    # create a binary mask.
    mask = ndvi_avg.neq(0)

    # define projection attributes
    image_proj = ndvi_1yr.projection()

    # reproject land cover, soil_tax_usda and avhrr to modis resolution
    lc_proj = lc_t0.reproject(crs=image_proj)
    soil_tax_usda_proj = soil_tax_usda.reproject(crs=image_proj)
    ndvi_avg_proj = ndvi_avg.reproject(crs=image_proj)

    # define unit of analysis as the intersect of soil_tax_usda and land cover
    units = soil_tax_usda_proj.multiply(100).add(lc_proj)

    # create a 2 band raster to compute 90th percentile per unit (analysis restricted by mask and study area)
    ndvi_id = ndvi_avg_proj.addBands(units).updateMask(mask)

    # compute 90th percentile by unit
    perc90 = ndvi_id.reduceRegion(reducer=ee.Reducer.percentile([90]).
                                  group(groupField=1, groupName='code'),
                                  geometry=poly,
                                  scale=ee.Number(modis_proj.nominalScale()).getInfo(),
                                  maxPixels=1e15)

    # Extract the cluster IDs and the 90th percentile
    groups = ee.List(perc90.get("groups"))
    ids = groups.map(lambda d: ee.Dictionary(d).get('code'))
    perc = groups.map(lambda d: ee.Dictionary(d).get('p90'))

    # remap the units raster using their 90th percentile value
    raster_perc = units.remap(ids, perc)

    # compute the ration of observed ndvi to 90th for that class
    obs_ratio = ndvi_avg_proj.divide(raster_perc)

    # aggregate obs_ratio to original NDVI data resolution (for modis this step does not change anything)
    obs_ratio_2 = obs_ratio.reduceResolution(reducer=ee.Reducer.mean(), maxPixels=2000) \
        .reproject(crs=ndvi_1yr.projection())

    # create final degradation output layer (9999 is background), 0 is not
    # degreaded, -1 is degraded
    lp_perf_deg = ee.Image(-32768).where(obs_ratio_2.gte(0.5), 0) \
        .where(obs_ratio_2.lte(0.5), -1)

    return ee.Image(lp_perf_deg.addBands(obs_ratio_2.multiply(10000)).addBands(units).unmask(-32768).int16())

def productivity_state(year_bl_start, year_bl_end,
                       year_tg_start, year_tg_end,
                       ndvi_1yr):
    
    ndvi_1yr = ee.Image(ndvi_1yr)

    # compute min and max of annual ndvi for the baseline period
    bl_ndvi_range = ndvi_1yr.select(ee.List(['y{}'.format(i) for i in range(year_bl_start, year_bl_end + 1)])) \
        .reduce(ee.Reducer.percentile([0, 100]))

    # add two bands to the time series: one 5% lower than min and one 5% higher than max
    bl_ndvi_ext = ndvi_1yr.select(ee.List(['y{}'.format(i) for i in range(year_bl_start, year_bl_end + 1)])) \
        .addBands(bl_ndvi_range.select('p0').subtract((bl_ndvi_range.select('p100').subtract(bl_ndvi_range.select('p0'))).multiply(0.05)))\
        .addBands(bl_ndvi_range.select('p100').add((bl_ndvi_range.select('p100').subtract(bl_ndvi_range.select('p0'))).multiply(0.05)))

    # compute percentiles of annual ndvi for the extended baseline period
    percentiles = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    bl_ndvi_perc = bl_ndvi_ext.reduce(ee.Reducer.percentile(percentiles))

    # compute mean ndvi for the baseline and target period period
    bl_ndvi_mean = ndvi_1yr.select(ee.List(['y{}'.format(i) for i in range(year_bl_start, year_bl_end + 1)])) \
        .reduce(ee.Reducer.mean()).rename(['ndvi'])
    tg_ndvi_mean = ndvi_1yr.select(ee.List(['y{}'.format(i) for i in range(year_tg_start, year_tg_end + 1)])) \
        .reduce(ee.Reducer.mean()).rename(['ndvi'])

    # reclassify mean ndvi for baseline period based on the percentiles
    bl_classes = ee.Image(-32768) \
        .where(bl_ndvi_mean.lte(bl_ndvi_perc.select('p10')), 1) \
        .where(bl_ndvi_mean.gt(bl_ndvi_perc.select('p10')), 2) \
        .where(bl_ndvi_mean.gt(bl_ndvi_perc.select('p20')), 3) \
        .where(bl_ndvi_mean.gt(bl_ndvi_perc.select('p30')), 4) \
        .where(bl_ndvi_mean.gt(bl_ndvi_perc.select('p40')), 5) \
        .where(bl_ndvi_mean.gt(bl_ndvi_perc.select('p50')), 6) \
        .where(bl_ndvi_mean.gt(bl_ndvi_perc.select('p60')), 7) \
        .where(bl_ndvi_mean.gt(bl_ndvi_perc.select('p70')), 8) \
        .where(bl_ndvi_mean.gt(bl_ndvi_perc.select('p80')), 9) \
        .where(bl_ndvi_mean.gt(bl_ndvi_perc.select('p90')), 10)

    # reclassify mean ndvi for target period based on the percentiles
    tg_classes = ee.Image(-32768) \
        .where(tg_ndvi_mean.lte(bl_ndvi_perc.select('p10')), 1) \
        .where(tg_ndvi_mean.gt(bl_ndvi_perc.select('p10')), 2) \
        .where(tg_ndvi_mean.gt(bl_ndvi_perc.select('p20')), 3) \
        .where(tg_ndvi_mean.gt(bl_ndvi_perc.select('p30')), 4) \
        .where(tg_ndvi_mean.gt(bl_ndvi_perc.select('p40')), 5) \
        .where(tg_ndvi_mean.gt(bl_ndvi_perc.select('p50')), 6) \
        .where(tg_ndvi_mean.gt(bl_ndvi_perc.select('p60')), 7) \
        .where(tg_ndvi_mean.gt(bl_ndvi_perc.select('p70')), 8) \
        .where(tg_ndvi_mean.gt(bl_ndvi_perc.select('p80')), 9) \
        .where(tg_ndvi_mean.gt(bl_ndvi_perc.select('p90')), 10)

    # difference between start and end clusters >= 2 means improvement (<= -2 
    # is degradation)
    classes_chg = tg_classes.subtract(bl_classes).where(bl_ndvi_mean.subtract(tg_ndvi_mean).abs().lte(100), 0)

    return ee.Image(classes_chg.addBands(bl_classes).addBands(tg_classes).addBands(bl_ndvi_mean).addBands(tg_ndvi_mean).int16())

# TODO need to combile the results from the three function to get the final out put