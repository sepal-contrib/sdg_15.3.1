###############################
##      renaming images      ##
###############################

def rename_band(img, sensor):
    
    if sensor in ['Landsat 4', 'Landsat 5', 'Landsat 7']:
        img = img.select(['B3', 'B4', 'pixel_qa'],['Red', 'NIR',  'pixel_qa'])
    elif sensor == 'Landsat 8':
        img = img.select(['B4', 'B5', 'pixel_qa'],['Red', 'NIR', 'pixel_qa']) 
    elif sensor == 'Sentinel 2':
        img = img.select(['B8', 'B4', 'QA60'],['Red', 'NIR', 'QA60'])
        
    return img

################################
##      masking function      ##
################################

def cloud_mask(img, sensor):
    
    if sensor in ['Landsat 4', 'Landsat 5', 'Landsat 7', 'landsat 8']:
        
        cloudsBitMask = 1 << 5
        qa = img.select('pixel_qa')
        mask = qa.bitwiseAnd(cloudsBitMask).eq(0)
        
        img = img.updateMask(mask)
    
    elif sensor == 'Sentilel 2':
        
        qa = img.select(['QA60'])
        
        img = img.updateMask(qa.lt(1))
        
    return img

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
    for year in range(year_start, year_end+1):
        # get the precipitation img
        prec_img = precipitation \
            .filterDate(f'{year}-01-01', '{year}-12-31') \
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

def f_img_coll(climate_1yr, ndvi_stack, start, end):
    """missing descriptions"""
    
    img_coll = ee.List([])
    for year in range(start, end + 1):
        
        ndvi_img = ndvi_stack \
            .filter(ee.Filter.eq('year', year)) \
            .first() \
            .select('ndvi') \
            .addBands(
                climate_1yr \
                .filter(ee.Filter.eq('year', year)) \
                .first() \
                .select('clim')
            ) \
            .rename(['ndvi', 'clim']) \
            .set({'year': year})
        
        img_coll = img_coll.add(ndvi_img)
    
    return ee.ImageCollection(img_coll)


def f_ndvi_clim_p(image, list, lf_clim_ndvi):
    """predict NDVI from climate"""
    
    ndvi = lf_clim_ndvi \
        .select('offset') \
        .add((lf_clim_ndvi.select('scale').multiply(image))) \
        .set({'year': image.get('year')})
    
    return ee.List(list).add(ndvi)

def stack(start, end, ndvi_1yr_o, clim_1yr_o):
    """Function to compute differences between observed and predicted NDVI and compilation in an image collection"""
    
    img_coll = ee.List([])
    for year in range(start, end + 1):
            
        ndvi = ndvi_1yr_o \
            .filter(ee.Filter.eq('year', year)) \
            .select('ndvi') \
            .median()
        
        clim = clim_1yr_o \
            .filter(ee.Filter.eq('year', year)) \
            .select('ndvi') \
            .median()
            
        img = ndvi \
            .addBands(clim.addBands(ee.Image(k).float())) \
            .rename(['ndvi', 'clim', 'year']) \
            .set({'year': year})
        
        # add to the image collection
        img_coll = img_coll.add(img)
    
    return ee.ImageCollection(img_coll)

def f_ndvi_clim_r_img(year, ndvi_1yr_coll, ndvi_1yr_p):
    """Function to compute residuals (ndvi obs - ndvi pred)"""
    
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

def f_ndvi_clim_r_coll(start, end, ndvi_1yr_coll, ndvi_1yr_p):
    """Function create image collection of residuals"""
        
    res_list = ee.List([])
    for year in range(start, end + 1):
            
        res_image = f_ndvi_clim_r_img(year, ndvi_1yr_coll, ndvi_1yr_p)
        
        res_list = res_list.add(res_image)
        
    return ee.ImageCollection(res_list)

def f_img_coll(start, end, ndvi_stack, climate_1yr):
    """missing description"""
        
    img_coll = ee.List([])
    for year in range(start, end + 1):
        
        ndvi_img = ndvi_stack \
            .filter(ee.Filter.eq('year', year)) \
            .median() \
            .select('ndvi')
            
        clim_img = climate_1yr \
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