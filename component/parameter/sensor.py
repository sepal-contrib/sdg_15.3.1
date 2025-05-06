# first images year
L4_start = 1982

# max year for land cover
land_cover_max_year = 2022
sensor_max_year = 2024

land_cover_first_year = 1992

# name of the sensor, GEE asset
sensors = {
    "Landsat 4": ["LANDSAT/LT04/C02/T1_L2", 30, "l4", "SR"],
    "Derived VI Landsat": [
        ["LANDSAT/COMPOSITES/C02/T1_L2_32DAY_NDVI", "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_EVI"],
        30,
        "",
        "VI",
    ],
    "Landsat 5": ["LANDSAT/LT05/C02/T1_L2", 30, "l5", "SR"],
    "Landsat 7": ["LANDSAT/LE07/C02/T1_L2", 30, "l7", "SR"],
    "MODIS MOD13Q1": ["MODIS/061/MOD13Q1", 250, "modis", ""],
    "Terra NPP": ["MODIS/006/MOD17A3HGF", 250, "modis", ""],
    "MODIS MYD13Q1": ["MODIS/061/MYD13Q1", 250, "modis", ""],
    "Landsat 8": ["LANDSAT/LC08/C02/T1_L2", 30, "l8", "SR"],
    "Sentinel 2": ["COPERNICUS/S2_SR_HARMONIZED", 10, "s2", "SR"],
    "Landsat 9": ["LANDSAT/LC09/C02/T1_L2", 30, "l9", "SR"],
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
