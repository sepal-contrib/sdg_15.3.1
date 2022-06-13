# first images year
L4_start = 1982

# max year for land cover
land_cover_max_year = 2020
sensor_max_year = 2021

land_cover_first_year = 1992

# name of the sensor, GEE asset
sensors = {
    "Derived VI Landsat 4": [
        ["LANDSAT/LT04/C01/T1_32DAY_NDVI", "LANDSAT/LT04/C01/T1_32DAY_EVI"],
        30,
        "l4",
        "VI",
    ],
    "Landsat 4": ["LANDSAT/LT04/C01/T1_SR", 30, "l4", "SR"],
    "Derived VI Landsat 5": [
        ["LANDSAT/LT05/C01/T1_32DAY_NDVI", "LANDSAT/LT05/C01/T1_32DAY_EVI"],
        30,
        "",
        "VI",
    ],
    "Landsat 5": ["LANDSAT/LT05/C01/T1_SR", 30, "l5", "SR"],
    "Derived VI Landsat 7": [
        ["LANDSAT/LE07/C01/T1_32DAY_NDVI", "LANDSAT/LE07/C01/T1_32DAY_EVI"],
        30,
        "l7",
        "VI",
    ],
    "Landsat 7": ["LANDSAT/LE07/C01/T1_SR", 30, "l7", "SR"],
    "MODIS MOD13Q1": ["MODIS/061/MOD13Q1", 250, "modis", ""],
    "Terra NPP": ["MODIS/006/MOD17A3HGF", 250, "modis", ""],
    "MODIS MYD13Q1": ["MODIS/061/MYD13Q1", 250, "modis", ""],
    "Derived VI Landsat 8": [
        ["LANDSAT/LC08/C01/T1_32DAY_NDVI", "LANDSAT/LC08/C01/T1_32DAY_EVI"],
        30,
        "l8",
        "VI",
    ],
    "Landsat 8": ["LANDSAT/LC08/C01/T1_SR", 30, "l8", "SR"],
    "Sentinel 2": ["COPERNICUS/S2", 10, "s2", "SR"],
}


precipitation = "NOAA/PERSIANN-CDR"

land_cover_ic = "users/amitghosh/sdg_module/esa/cci_landcover"
jrc_water = "JRC/GSW1_3/GlobalSurfaceWater"
soil_taxonomy = "OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02"
soc = "users/geflanddegradation/toolbox_datasets/soc_sgrid_30cm"
soc_isric = "projects/soilgrids-isric/soc_mean"
ipcc_climate_zones = "users/geflanddegradation/toolbox_datasets/ipcc_climate_zones"
wte = "users/amitghosh/sdg_module/wte_2020"
gaes = "users/amitghosh/sdg_module/fao/GAES_L4"
aez = "users/amitghosh/sdg_module/fao/aez_v9v2_CRUTS32_Hist_8110_100_avg"
hru = "users/amitghosh/sdg_module/hru_250"
