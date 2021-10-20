# first images year
L4_start = 1982

# max year for land cover
land_cover_max_year = 2019
sensor_max_year = 2020

land_cover_first_year = 1992

# name of the sensor, GEE asset
sensors = {
    "Landsat 4": ["LANDSAT/LT04/C01/T1_SR", 30],
    "Landsat 5": ["LANDSAT/LT05/C01/T1_SR", 30],
    "Landsat 7": ["LANDSAT/LE07/C01/T1_SR", 30],
    "MODIS MOD13Q1": ["MODIS/006/MOD13Q1", 250],
    "MODIS NPP": ["MODIS/006/MOD17A3HGF", 250],
    "Landsat 8": ["LANDSAT/LC08/C01/T1_SR", 30],
    "Sentinel 2": ["COPERNICUS/S2", 10],
}

precipitation = "NOAA/PERSIANN-CDR"

land_cover = "users/amitghosh/sdg_module/esa_cci_lc_1992_2019"
soil_taxonomy = "OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02"
soc = "users/geflanddegradation/toolbox_datasets/soc_sgrid_30cm"
soc_isric = "projects/soilgrids-isric/soc_mean"
ipcc_climate_zones = "users/geflanddegradation/toolbox_datasets/ipcc_climate_zones"
wte = "users/amitghosh/sdg_module/wte_2020"
