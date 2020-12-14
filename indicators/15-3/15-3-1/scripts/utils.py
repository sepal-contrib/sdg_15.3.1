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

