# first images year
L4_start = 1982

# max year for land cover 
land_cover_max_year = 2019
sensor_max_year = 2020

land_cover_first_year = 1992

# name of the sensor, GEE asset
sensors = {
        'Landsat 4': 'LANDSAT/LT04/C01/T1_SR',
        'Landsat 5': 'LANDSAT/LT05/C01/T1_SR',
        'Landsat 7': 'LANDSAT/LE07/C01/T1_SR', 
        'Landsat 8': 'LANDSAT/LC08/C01/T1_SR', 
        'Sentinel 2': 'COPERNICUS/S2'
}

precipitation = 'NOAA/PERSIANN-CDR'

land_cover = "users/amitghosh/sdg_module/esa_cci_lc_1992_2019"
soil_tax = "users/geflanddegradation/toolbox_datasets/soil_tax_usda_sgrid"
soc = "users/geflanddegradation/toolbox_datasets/soc_sgrid_30cm"
ipcc_climate_zones = "users/geflanddegradation/toolbox_datasets/ipcc_climate_zones"
