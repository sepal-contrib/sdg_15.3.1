from zipfile import ZipFile
import time

import ee
import geemap
from ipywidgets import Output
import ipyvuetify as v
import geopandas as gpd
import pandas as pd

from component import parameter as pm
from component.message import ms 

from .gdrive import gdrive
from .gee import wait_for_completion
from .download import digest_tiles
from .integration import * 
from .productivity import *
from .soil_organic_carbon import *
from .land_cover import *

ee.Initialize()

def download_maps(aoi_model, model, output):
    
    # get the export scale 
    scale = 10 if 'Sentinel 2' in model.sensors else 30
    
    output.add_live_msg(ms.download.start_download)
        
    # create the export path
    land_cover_desc = f'{aoi_model.name}_land_cover'
    soc_desc = f'{aoi_model.name}_soc'
    productivity_desc = f'{aoi_model.name}_productivity'
    indicator_desc = f'{aoi_model.name}_indicator_15_3_1'
        
    # load the drive_handler
    drive_handler = gdrive()
    
    # clip the images if it's an administrative layer and keep the bounding box if not
    if aoi_model.feature_collection:
        geom = aoi_model.feature_collection.geometry()
        land_cover = model.land_cover.clip(geom)
        soc = model.soc.clip(geom)
        productivity = model.productivity.clip(geom)
        indicator = model.indicator_15_3_1.clip(geom)
    else:
        land_cover = model.land_cover
        soc = model.soc
        productivity = model.productivity
        indicator = model.indicator_15_3_1
        
    # download all files
    downloads = drive_handler.download_to_disk(land_cover_desc, land_cover, aoi_model, output)
    downloads = drive_handler.download_to_disk(soc_desc, soc, aoi_model, output)
    downloads = drive_handler.download_to_disk(productivity_desc, productivity, aoi_model, output)
    downloads = drive_handler.download_to_disk(indicator_desc, indicator, aoi_model, output)
        
    # I assume that they are always launch at the same time 
    # If not it's going to crash
    if downloads:
        wait_for_completion([land_cover_desc, soc_desc, productivity_desc, indicator_desc], output)
    output.add_live_msg(ms.gee.tasks_completed, 'success') 
    
    # create merge names 
    land_cover_merge = pm.result_dir.joinpath(f'{land_cover_desc}_merge.tif')
    soc_merge = pm.result_dir.joinpath(f'{soc_desc}_merge.tif')
    productivity_merge = pm.result_dir.joinpath(f'{productivity_desc}_merge.tif')
    indicator_merge = pm.result_dir.joinpath(f'{indicator_desc}_merge.tif')
    
    # digest the tiles
    digest_tiles(land_cover_desc, pm.result_dir, output, land_cover_merge)
    digest_tiles(soc_desc, pm.result_dir, output, soc_merge)
    digest_tiles(productivity_desc, pm.result_dir, output, productivity_merge)
    digest_tiles(indicator_desc, pm.result_dir, output, indicator_merge)
        
    output.add_live_msg(ms.download.remove_gdrive)
    # remove the files from drive
    drive_handler.delete_files(drive_handler.get_files(land_cover_desc))
    drive_handler.delete_files(drive_handler.get_files(soc_desc))
    drive_handler.delete_files(drive_handler.get_files(productivity_desc))
    drive_handler.delete_files(drive_handler.get_files(indicator_desc))
        
    #display msg 
    output.add_live_msg(ms.download.completed, 'success')

    return (land_cover_merge, soc_merge, productivity_merge, indicator_merge)

def display_maps(aoi_model, model, m, output):
    
    m.zoom_ee_object(aoi_model.feature_collection.geometry())
    
    # get the geometry to clip on 
    geom = aoi_model.feature_collection.geometry()
    
    # clip on the bounding box when we use a custom aoi
    if not ('ADMIN' in aoi_model.method): 
        geom = geom.bounds()
        
    # add the layers
    output.add_live_msg(ms.gee.add_layer.format(ms._15_3_1.prod_layer))
    m.addLayer(model.productivity.clip(geom), pm.viz_prod, ms._15_3_1.prod_layer)
    
    output.add_live_msg(ms.gee.add_layer.format(ms._15_3_1.lc_layer))
    m.addLayer(model.land_cover.select('degradation').clip(geom), pm.viz_lc, ms._15_3_1.lc_layer)
    
    output.add_live_msg(ms.gee.add_layer.format(ms._15_3_1.soc_layer))
    m.addLayer(model.soc.clip(geom), pm.viz_soc, ms._15_3_1.soc_layer)
    
    output.add_live_msg(ms.gee.add_layer.format(ms._15_3_1.ind_layer))
    m.addLayer(model.indicator_15_3_1.clip(geom), pm.viz_indicator, ms._15_3_1.ind_layer)
        
    # add the aoi on the map
    m.addLayer(aoi_model.feature_collection, {'color': v.theme.themes.dark.info}, 'aoi')
    
    return 

def compute_indicator_maps(aoi_model, model, output):
    
    # raise an error if the years are not in the rigth order 
    if not (model.start <model.baseline_end <= model.target_start < model.end):
        raise Exception(ms._15_3_1.error.wrong_year)
    
    # compute intermediary maps 
    ndvi_int, climate_int = integrate_ndvi_climate(aoi_model, model, output)
    prod_trajectory = productivity_trajectory(model, ndvi_int, climate_int, output)
    prod_performance = productivity_performance(aoi_model, model, ndvi_int, climate_int, output)
    prod_state = productivity_state(aoi_model, model, ndvi_int, climate_int, output) 
    
    # compute result maps 
    model.land_cover = land_cover(model, aoi_model, output)
    model.soc = soil_organic_carbon(model, aoi_model, output)
    model.productivity = productivity_final(prod_trajectory, prod_performance, prod_state, output)
    
    # sump up in a map
    model.indicator_15_3_1 = indicator_15_3_1(model.productivity, model.land_cover, model.soc, output)

    return 

def compute_zonal_analysis(aoi_model, model, output):
    
    indicator_stats = pm.result_dir.joinpath(f'{aoi_model.name}_indicator_15_3_1')
    
    #check if the file already exist
    indicator_zip = indicator_stats.with_suffix('.zip')
    if indicator_zip.is_file():
        output.add_live_msg(ms.download.already_exist.format(indicator_zip), 'warning')
        time.sleep(2)
        return indicator_zip
        
    output_widget = Output()
    output.add_msg(output_widget)
        
    indicator_csv = indicator_stats.with_suffix('.csv') # to be removed when moving to shp
    scale = 100 if 'Sentinel 2' in model.sensors else 300
    with output_widget:
        geemap.zonal_statistics_by_group(
            in_value_raster = model.indicator_15_3_1,
            in_zone_vector = aoi_model.feature_collection,
            out_file_path = indicator_csv,
            statistics_type = "SUM",
            denominator = 1000000,
            decimal_places = 2,
            scale = scale,
            tile_scale = 1.0
        )
    # this should be removed once geemap is repaired
    #########################################################################
    aoi_json = geemap.ee_to_geojson(aoi_model.feature_collection)
    aoi_gdf = gpd.GeoDataFrame.from_features(aoi_json).set_crs('EPSG:4326')
    
    indicator_df = pd.read_csv(indicator_csv)
    if 'Class_0' in indicator_df.columns:
        aoi_gdf['NoData'] = indicator_df['Class_0']
    if 'Class_3' in indicator_df.columns:
        aoi_gdf['Improve'] = indicator_df['Class_3']
    if 'Class_2' in indicator_df.columns:
        aoi_gdf['Stable'] = indicator_df['Class_2']
    if 'Class_1' in indicator_df.columns:
        aoi_gdf['Degrade'] = indicator_df['Class_1']
    aoi_gdf = aoi_gdf[aoi_gdf.geom_type !="LineString"]
    aoi_gdf.to_file(indicator_stats.with_suffix('.shp'))
    #########################################################################
    
    # get all the shp extentions
    suffixes = ['.dbf', '.prj', '.shp', '.cpg', '.shx'] # , '.fix']
    
    # write the zip file
    with ZipFile(indicator_zip, 'w') as myzip:
        for suffix in suffixes:
            file = indicator_stats.with_suffix(suffix)
            myzip.write(file, file.name)
            
    output.add_live_msg(ms._15_3_1.stats_complete.format(indicator_zip), 'success')
        
    return indicator_zip
    
def indicator_15_3_1(productivity, landcover, soc, output):
    
    water = landcover.select('water')
    landcover = landcover.select('degradation')

    indicator = ee.Image(0) \
    .where(productivity.eq(3).And(landcover.eq(3)).And(soc.eq(3)),3) \
    .where(productivity.eq(3).And(landcover.eq(3)).And(soc.eq(2)),3) \
    .where(productivity.eq(3).And(landcover.eq(3)).And(soc.eq(1)),1) \
    .where(productivity.eq(3).And(landcover.eq(2)).And(soc.eq(3)),3) \
    .where(productivity.eq(3).And(landcover.eq(2)).And(soc.eq(2)),3) \
    .where(productivity.eq(3).And(landcover.eq(2)).And(soc.eq(1)),1) \
    .where(productivity.eq(3).And(landcover.eq(1)).And(soc.eq(3)),1) \
    .where(productivity.eq(3).And(landcover.eq(1)).And(soc.eq(2)),1) \
    .where(productivity.eq(3).And(landcover.eq(1)).And(soc.eq(1)),1) \
    .where(productivity.eq(2).And(landcover.eq(3)).And(soc.eq(3)),3) \
    .where(productivity.eq(2).And(landcover.eq(3)).And(soc.eq(2)),3) \
    .where(productivity.eq(2).And(landcover.eq(3)).And(soc.eq(1)),1) \
    .where(productivity.eq(2).And(landcover.eq(2)).And(soc.eq(3)),3) \
    .where(productivity.eq(2).And(landcover.eq(2)).And(soc.eq(2)),2) \
    .where(productivity.eq(2).And(landcover.eq(2)).And(soc.eq(1)),1) \
    .where(productivity.eq(2).And(landcover.eq(1)).And(soc.eq(3)),1) \
    .where(productivity.eq(2).And(landcover.eq(1)).And(soc.eq(2)),1) \
    .where(productivity.eq(2).And(landcover.eq(1)).And(soc.eq(1)),1) \
    .where(productivity.eq(1).And(landcover.eq(3)).And(soc.eq(3)),1) \
    .where(productivity.eq(1).And(landcover.eq(3)).And(soc.eq(2)),1) \
    .where(productivity.eq(1).And(landcover.eq(3)).And(soc.eq(1)),1) \
    .where(productivity.eq(1).And(landcover.eq(2)).And(soc.eq(3)),1) \
    .where(productivity.eq(1).And(landcover.eq(2)).And(soc.eq(2)),1) \
    .where(productivity.eq(1).And(landcover.eq(2)).And(soc.eq(1)),1) \
    .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(3)),1) \
    .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(2)),1) \
    .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(1)),1) \
    .where(productivity.eq(1).And(landcover.lt(1)).And(soc.lt(1)),1) \
    .where(productivity.lt(1).And(landcover.eq(1)).And(soc.lt(1)),1) \
    .where(productivity.lt(1).And(landcover.lt(1)).And(soc.eq(1)),1) \
    .where(productivity.eq(2).And(landcover.lt(1)).And(soc.lt(1)),2) \
    .where(productivity.lt(1).And(landcover.eq(2)).And(soc.lt(1)),2) \
    .where(productivity.lt(1).And(landcover.lt(1)).And(soc.eq(2)),2) \
    .where(productivity.eq(3).And(landcover.lt(1)).And(soc.lt(1)),3) \
    .where(productivity.lt(1).And(landcover.eq(3)).And(soc.lt(1)),3) \
    .where(productivity.lt(1).And(landcover.lt(1)).And(soc.eq(3)),3) \
    .updateMask(water)
    
    return indicator.uint8()
