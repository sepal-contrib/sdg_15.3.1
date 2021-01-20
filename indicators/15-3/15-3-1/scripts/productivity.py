from functools import partial

import ee

from scripts import parameter as pm
from scripts import utils as u

ee.Initialize()

def ndvi_trend(start, end, ndvi_yearly_integration):
    """Calculate NDVI trend.
    
    Calculates the trend of temporal NDVI using NDVI data from selected satellite dataset. Areas where changes are not significant
    are masked out using a Mann-Kendall test.
    """

    ## Compute linear trend function to predict ndvi based on year (ndvi trend)
    lf_trend = ndvi_yearly_integration \
        .select(['year', 'ndvi']) \
        .reduce(ee.Reducer.linearFit())

    ## Compute Kendall statistics
    mk_trend = u.mann_kendall(ndvi_yearly_integration.select('ndvi'))

    return (lf_trend, mk_trend)

def p_restrend(start, end, nvdi_yearly_integration, climate_yearly_integration):
    """Rasudial trend analsis predicts NDVI based on the given rainfall. p_restrend uses linear regression model to predict NDVI for a given rainfall amount. The residual (Predicted - Obsedved)NDVI trend is considered as productivity change that is indipendent of climatic variation. For further details, check the reference: Wessels, K.J.; van den Bergh, F.; Scholes, R.J. Limits to detectability of land degradation by trend analysis of vegetation index data. Remote Sens. Environ. 2012, 125, 10–22.
    """
    
    ## Apply function to create image collection of ndvi and climate
    ndvi_climate_yearly_integration = ndvi_climate_merge(climate_yearly_integration, nvdi_yearly_integration, start, end)

    ## Compute linear trend function to predict ndvi based on climate (independent are followed by dependent var
    linear_model_climate_ndvi = ndvi_climate_yearly_integration \
        .select(['clim', 'ndvi']) \
        .reduce(ee.Reducer.linearFit())

    ## Apply function to  predict NDVI based on climate
    predicted_yearly_ndvi = ee.ImageCollection(ee.List(
        ndvi_climate_yearly_integration \
        .select('clim') \
        .iterate(partial(ndvi_prediction_climate, linear_model_climate_ndvi = linear_model_climate_ndvi), first)
    ))

    ## Apply function to compute NDVI annual residuals
    residual_yearly_ndvi = image_collection_residuals(io.start, io.end, nvdi_yearly_integration, predicted_yearly_ndvi)

    ## Fit a linear regression to the NDVI residuals
    lf_trend = residual_yearly_ndvi.select(['year', 'ndvi_res']).reduce(ee.Reducer.linearFit())

    ## Compute Kendall statistics
    mk_trend = u.mann_kendall(residual_yearly_ndvi.select('ndvi_res'))
    
    return (lf_trend, mk_trend)

def ue_trend(start, end, nvdi_yearly_integration, climate_yearly_integration):
    """Calculate trend based on rain use efficiency.
    It is the ratio of ANPP(annual integral of NDVI as proxy) to annual precipitation.

    """

    # Convert the climate layer to meters (for precip) so that RUE layer can be
    # scaled correctly
    # TODO: Need to handle scaling for ET for WUE
    
    # Apply function to compute ue and store as a collection
    ue_yearly_collection = use_efficiency(climate_yearly_integration, nvdi_yearly_integration, start, end)

    # Compute linear trend function to predict ndvi based on year (ndvi trend)
    lf_trend = ue_yearly_collection.select(['year', 'ue']).reduce(ee.Reducer.linearFit())

    # Compute Kendall statistics
    trend = u.mann_kendall(ue_yearly_collection.select('ue'))
    
    return (lf_trend, mk_trend)

##############################
##      index creation      ##
##############################

def CalcNDVI(img):
    """compute the ndvi on renamed bands"""
    
    red = img.select('Red')
    nir = img.select('NIR')
    
    ndvi = nir.subtract(red) \
        .divide(nir.add(red)) \
        .rename('ndvi') \
        .set('system:time_start', img.get('system:time_start'))
    
    return ndvi

#####################################
##      integration functions      ##
#####################################

def int_yearly_ndvi(ndvi_coll, start, end):
    """Function to integrate observed NDVI datasets at the annual level"""
    
    img_coll = ee.List([])
    for year in range(start, end + 1):
        # get the ndvi img
        ndvi_img = ndvi_coll \
            .filterDate(f'{year}-01-01', f'{year}-12-31') \
            .reduce(ee.Reducer.mean()) \
            .rename('ndvi')
        
        # convert to float
        con_img = ee.Image(year).float().rename('year')
        img = ndvi_img.addBands(con_img).set({'year': year})
        
        # append to the collection
        img_coll = img_coll.add(img)
        
    return ee.ImageCollection(img_coll)

def int_yearly_climate(precipitation, start, end):
    """Function to integrate observed precipitation datasets at the annual level"""
    
    img_coll = ee.List([])
    for year in range(start, end+1):
        # get the precipitation img
        prec_img = precipitation \
            .filterDate(f'{year}-01-01', f'{year}-12-31') \
            .reduce(ee.Reducer.sum()) \
            .rename('clim')
        
        # convert to float
        con_img = ee.Image(year).float().rename('year')
        img = prec_img.addBands(con_img).set({'year': year})
        
        # append to the collection
        img_coll = img_coll.add(img)
        
    return ee.ImageCollection(img_coll)


#############################
##      kendall index      ##
#############################

def mann_kendall(imageCollection):
    """Calculate Mann Kendall's S statistic.
    This function returns the Mann Kendall's S statistic, assuming that n is
    less than 40. The significance of a calculated S statistic is found in
    table A.30 of Nonparametric Statistical Methods, second edition by
    Hollander & Wolfe.
    Args:
        imageCollection: A Google Earth Engine image collection.
    Returns:
        A Google Earth Engine image collection with Mann Kendall statistic for
            each pixel.
    """
    
    TimeSeriesList = imageCollection.toList(50)
    
    NumberOfItems = TimeSeriesList.length().getInfo()
    ConcordantArray = []
    DiscordantArray = []
    for i in range(0, NumberOfItems - 1):
        
        CurrentImage = ee.Image(TimeSeriesList.get(i))
        
        for j in range(i + 1, NumberOfItems):
            
            nextImage = ee.Image(TimeSeriesList.get(j))
            
            Concordant = CurrentImage.lt(nextImage)
            ConcordantArray.append(Concordant)
            
            Discordant = CurrentImage.gt(nextImage)
            DiscordantArray.append(Discordant)
            
    ConcordantSum = ee.ImageCollection(ConcordantArray).sum()
    DiscordantSum = ee.ImageCollection(DiscordantArray).sum()
    
    MKSstat = ConcordantSum.subtract(DiscordantSum)
    
    return MKSstat

##################################
##      image manipulation      ##
##################################

def ndvi_climate_merge(climate_yearly_integration, nvdi_yearly_integration, start, end):
    """Creat an ImageCollection of annual integral of NDVI and annual inegral of climate data"""
    
    img_list = ee.List([])
    for year in range(start, end + 1):
        
        ndvi_img = nvdi_yearly_integration \
            .filter(ee.Filter.eq('year', year)) \
            .first() \
            .select('ndvi') \
            .addBands(
                climate_yearly_integration \
                .filter(ee.Filter.eq('year', year)) \
                .first() \
                .select('clim')
            ) \
            .rename(['ndvi', 'clim']) \
            .set({'year': year})
        
        img_list = img_list.add(ndvi_img)
    
    out = ee.ImageCollection(img_list)
    
    return out

def ndvi_prediction_climate(image, list_, linear_model_climate_ndvi):
    """predict NDVI from climate. part of p_restrend function"""
    
    ndvi = linear_model_climate_ndvi \
        .select('offset') \
        .add((lf_clim_ndvi.select('scale').multiply(image))) \
        .set({'year': image.get('year')})
    
    return ee.List(list_).add(ndvi)

def ndvi_residuals(year, ndvi_climate_yearly_integration, predicted_yearly_ndvi):
    """Function to compute residuals (ndvi obs - ndvi pred). part of p_restrend function"""
    
    ndvi_o = ndvi_1yr_coll \
        .filter(ee.Filter.eq('year', year)) \
        .select('ndvi') \
        .median()
    
    ndvi_p = ndvi_1yr_p \
        .filter(ee.Filter.eq('year', year)) \
        .median()
    
    ndvi_r = ee.Image(year) \
        .float() \
        .addBands(ndvi_o.subtract(ndvi_p))
    
    return ndvi_r.rename(['year', 'ndvi_res'])

def image_collection_residuals(start, end, ndvi_climate_yearly_integration, predicted_yearly_ndvi):
    """Function to create image collection of residuals. part of p_restrend function"""
        
    res_list = ee.List([])
    for year in range(start, end + 1):
            
        res_image = ndvi_residuals(year, ndvi_climate_yearly_integration, predicted_yearly_ndvi)
        
        res_list = res_list.add(res_image)
        
    return ee.ImageCollection(res_list)

def use_efficiency(start, end, ndvi_yearly_integration, climate_yearly_integration):
    """Function to creat rain use efficiency and store as an imageCollection"""
        
    img_coll = ee.List([])
    for year in range(start, end + 1):
        
        ndvi_img = ndvi_yearly_integration \
            .filter(ee.Filter.eq('year', year)) \
            .median() \
            .select('ndvi')
            
        clim_img = climate_yearly_integration \
            .filter(ee.Filter.eq('year', year)) \
            .median() \
            .select('clim') \
            .divide(1000)
            
        divide_img = ndvi_img \
            .divide(clim_img) \
            .addBands(ee.Image(year).float()) \
            .rename(['ue', 'year']) \
            .set({'year': k})
            
        img_coll = img_coll.add(divide_img)
        
    return ee.ImageCollection(img_coll)
