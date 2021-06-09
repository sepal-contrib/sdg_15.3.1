from functools import partial
import json

import ee 

from component import parameter as pm

ee.Initialize()

def integrate_ndvi_climate(aoi_model, model, output):
    
    # create the composite image collection
    i_img_coll = ee.ImageCollection([])
    
    for sensor in model.sensors:
        
        # get the image collection 
        # filter its bounds to fit the aoi extends 
        # rename the bands 
        # adapt the resolution to meet sentinel 2 native one (10m)
        # mask the clouds and adapt the scale 
        sat = ee.ImageCollection(pm.sensors[sensor]) \
            .filterBounds(aoi_model.feature_collection) \
            .map(partial(rename_band, sensor=sensor)) \
            .map(partial(adapt_res, sensor=sensor)) \
            .map(partial(cloud_mask, sensor=sensor)) 
    
        i_img_coll = i_img_coll.merge(sat)
    
    # Filtering the img collection  using start year and end year
    i_img_coll = i_img_coll.filterDate(f'{model.start}-01-01', f'{model.end}-12-31')

    # Function to integrate observed NDVI datasets at the annual level
    ndvi_coll = i_img_coll.map(CalcNDVI).select('ndvi')
    
    ndvi_int = int_yearly_ndvi(ndvi_coll, model.start, model.end)

    # process the climate dataset to use with the pixel restrend, RUE calculation
    precipitation = ee.ImageCollection(pm.precipitation) \
        .filterBounds(aoi_model.feature_collection) \
        .filterDate(f'{model.start}-01-01',f'{model.end}-12-31') \
        .select('precipitation')
    
    climate_int = int_yearly_climate(precipitation, model.start, model.end)
    
    return (ndvi_int, climate_int)

def rename_band(img, sensor):
    
    if sensor in ['Landsat 4', 'Landsat 5', 'Landsat 7']:
        img = img.select(['B3', 'B4', 'pixel_qa'],['Red', 'NIR',  'pixel_qa'])
    elif sensor == 'Landsat 8':
        img = img.select(['B4', 'B5', 'pixel_qa'],['Red', 'NIR', 'pixel_qa']) 
    elif sensor == 'Sentinel 2':
        img = img.select(['B4', 'B8', 'QA60'],['Red', 'NIR', 'QA60'])
        
    return img

def adapt_res(img, sensor):
    """reproject landasat images in the sentinel resolution"""
    
    # get sentinel projection
    sentinel_proj = ee.ImageCollection('COPERNICUS/S2').first().projection()
    
    # change landsat resolution 
    if sensor in ['landsat 8, Landsat 7, Landsat 5, Landsat 4']:
        img = img.changeProj(img.projection(), sentinel_proj)
        
    # the reflectance alignment won't be a problem as we don't use the bands per se but only the computed ndvi
        
    return img

def cloud_mask(img, sensor):
    """ mask the clouds based on the sensor name, sentine 2 data will be multiplyed by 10000 to meet the scale of landsat data"""

    if sensor in ['Landsat 5', 'Landsat 7', 'Landsat 4']:
        qa = img.select('pixel_qa')
        # If the cloud bit (5) is set and the cloud confidence (7) is high
        # or the cloud shadow bit is set (3), then it's a bad pixel.
        cloud = qa.bitwiseAnd(1 << 5).And(qa.bitwiseAnd(1 << 7)).Or(qa.bitwiseAnd(1 << 3))
        # Remove edge pixels that don't occur in all bands
        mask2 = img.mask().reduce(ee.Reducer.min())
            
        img =  img.updateMask(cloud.Not()).updateMask(mask2)
        
    elif sensor == 'Landsat 8':
        # Bits 3 and 5 are cloud shadow and cloud, respectively.
        cloudShadowBitMask = (1 << 3)
        cloudsBitMask = (1 << 5)
        # Get the pixel QA band.
        qa = img.select('pixel_qa')
        # Both flags should be set to zero, indicating clear conditions.
        mask = qa.bitwiseAnd(cloudShadowBitMask).eq(0).And(qa.bitwiseAnd(cloudsBitMask).eq(0))
            
        img = img.updateMask(mask)
        
    elif sensor == 'Sentinel 2':
        qa = img.select('QA60')
        # Bits 10 and 11 are clouds and cirrus, respectively.
        cloudBitMask = (1 << 10)
        cirrusBitMask = (1 << 11)
        # Both flags should be set to zero, indicating clear conditions.
        mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))
    
        img = img.updateMask(mask)#.divide(10000)
        
    return img 

def int_yearly_ndvi(ndvi_coll, start, end):
    """Function to integrate observed NDVI datasets at the annual level"""
    def daily_to_monthly_to_annual(year):
        
        ndvi_collection = ndvi_coll
        ndvi_coll_ann = ndvi_collection.filter(ee.Filter.calendarRange(year, field = 'year'))
        months = (ndvi_coll_ann.aggregate_array("system:time_start")
                .map(lambda x: ee.Number.parse(ee.Date(x).format("MM"))))
 

        img_coll= ee.ImageCollection.fromImages(
        months.map(lambda month:
                  ndvi_coll_ann \
                  .filter(ee.Filter.calendarRange(month, field = 'month')) \
                  .reduce(ee.Reducer.mean()))
             )
        img_coll_ndvi = img_coll \
            .reduce(ee.Reducer.mean()) \
            .float() \
            .rename('ndvi') \
            .addBands(ee.Image().constant(year).float().rename('year')) \
            .set('year',year)
        return img_coll_ndvi
    years = ee.List.sequence(start, end)
    img_coll = ee.ImageCollection.fromImages(
        years.map(daily_to_monthly_to_annual)
    )
   
    return img_coll

def int_yearly_climate(precipitation, start, end):
    """Function to integrate observed precipitation datasets at the annual level"""
    
    years = ee.List.sequence(start, end)
    
    img_coll = ee.ImageCollection.fromImages(
        years.map(lambda year:
            precipitation \
                .filter(ee.Filter.calendarRange(year, field = 'year')) \
                .reduce(ee.Reducer.mean()) \
                .rename('clim') \
                .addBands(ee.Image().constant(year).float().rename('year')) \
                .set('year', year)
        )
    )

def CalcNDVI(img):
    """compute the ndvi on renamed bands"""
    
    red = img.select('Red')
    nir = img.select('NIR')
    
    ndvi = nir.subtract(red) \
        .divide(nir.add(red)) \
        .multiply(10000) \
        .rename('ndvi') \
        .set('system:time_start', img.get('system:time_start'))
    
    return ndvi
