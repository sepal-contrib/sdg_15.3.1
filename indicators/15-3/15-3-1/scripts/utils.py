import time

import ee 

ee.Initialize()

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

##########################################
##      update landasat sensor res      ##
##########################################
def adapt_res(img, sensor):
    """reproject landasat images in the sentinel resolution"""
    
    # get sentinel projection
    sentinel_proj = ee.ImageCollection('COPERNICUS/S2').first().projection()
    
    # change landsat resolution 
    if sensor in ['landsat 8, Landsat 7, Landsat 5, Landsat 4']:
        img = img.changeProj(img.projection(), sentinel_proj)
        
    return img

################################
##      masking function      ##
################################

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

#messages 
STATUS = "Status : {0}"
    
def wait_for_completion(task_descripsion, output):
    """Wait until the selected process are finished. Display some output information

    Args:
        task_descripsion ([str]) : name of the running tasks
        widget_alert (v.Alert) : alert to display the output messages
    
    Returns: state (str) : final state
    """
    state = 'UNSUBMITTED'
    while not (state == 'COMPLETED' or state =='FAILED'):
        output.add_live_msg(STATUS.format(state))
        time.sleep(5)
                    
        #search for the task in task_list
        for task in task_descripsion:
            current_task = search_task(task)
            state = current_task.state
            if state == 'RUNNING': break
    
    return state

def search_task(task_descripsion):
    """Search for the described task in the user Task list return None if nothing is find
    
    Args: 
        task_descripsion (str): the task descripsion
    
    Returns
        task (ee.Task) : return the found task else None
    """
    
    tasks_list = ee.batch.Task.list()
    current_task = None
    for task in tasks_list:
        if task.config['description'] == task_descripsion:
            current_task = task
            break
            
    return current_task


