from zipfile import ZipFile
import time
from itertools import product

import ee
import geemap
from ipywidgets import Output
import ipyvuetify as v
import geopandas as gpd
import pandas as pd
from sepal_ui.scripts import utils as su

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

    # create a result folder including the data parameters
    # create the aoi and parameter folder if not existing
    aoi_dir = pm.result_dir / su.normalize_str(aoi_model.name)
    result_dir = aoi_dir / model.folder_name()
    result_dir.mkdir(parents=True, exist_ok=True)

    # get the export scale
    # from the first sensor (we only combine compatible one)
    scale = pm.sensors[model.sensors[0]][1]

    output.add_live_msg(ms.download.start_download)

    # create the export path
    # they are in correct order don't change it
    pattern = f"{aoi_model.name}_{model.folder_name()}"
    layers = {
        f"land_cover": model.land_cover,
        f"soc": model.soc,
        f"productivity_trend": model.productivity_trend,
        f"productivity_performance": model.productivity_performance,
        f"productivity_state": model.productivity_state,
        f"productivity_indicator": model.productivity,
        f"indicator_15_3_1": model.indicator_15_3_1,
    }

    # load the drive_handler
    drive_handler = gdrive()

    # clip the images if it's an administrative layer and keep the bounding box if not
    if aoi_model.feature_collection:
        geom = aoi_model.feature_collection.geometry()
        layers = {name: layer.clip(geom) for name, layer in layers.items()}

    # download all files
    downloads = any(
        [
            drive_handler.download_to_disk(
                name, layer, aoi_model, output, scale, f"{pattern}_{name}"
            )
            for name, layer in layers.items()
        ]
    )

    # I assume that they are always launch at the same time
    # If not it's going to crash
    if downloads:
        wait_for_completion([name for name in layers], output)
    output.add_live_msg(ms.gee.tasks_completed, "success")

    # digest the tiles
    for name in layers:
        digest_tiles(
            f"{pattern}_{name}",
            result_dir,
            output,
            result_dir / f"{pattern}_{name}_merge.tif",
        )

    output.add_live_msg(ms.download.remove_gdrive)

    # remove the files from drive
    for name in layers:
        drive_handler.delete_files(drive_handler.get_files(f"{pattern}_{name}"))

    # display msg
    output.add_live_msg(ms.download.completed, "success")

    return tuple([result_dir / f"{pattern}_{name}_merge.tif" for name in layers])


def display_maps(aoi_model, model, m, output):

    m.zoom_ee_object(aoi_model.feature_collection.geometry())

    # get the geometry to clip on
    geom = aoi_model.feature_collection.geometry()

    # clip on the bounding box when we use a custom aoi
    if not ("ADMIN" in aoi_model.method):
        geom = geom.bounds()

    viz_lc = {
        "min": min(model.lc_codelist_start),
        "max": max(model.lc_codelist_start),
        "palette": list(model.lc_color.values()),
    }

    # add the layers
    output.add_live_msg(ms.gee.add_layer.format(ms.lc_layer))
    m.addLayer(
        model.land_cover.select("start").clip(geom),
        viz_lc,
        ms.lc_start.format(model.lc_year_start_esa),
    )

    output.add_live_msg(ms.gee.add_layer.format(ms.lc_layer))
    m.addLayer(
        model.land_cover.select("end").clip(geom),
        viz_lc,
        ms.lc_end.format(model.lc_year_end_esa),
    )

    output.add_live_msg(ms.gee.add_layer.format(ms.prod_layer))
    m.addLayer(model.productivity.clip(geom).selfMask(), pm.viz_prod, ms.prod_layer)

    output.add_live_msg(ms.gee.add_layer.format(ms.lc_layer))
    m.addLayer(
        model.land_cover.select("degradation").clip(geom).selfMask(),
        pm.viz_lc_sub,
        ms.lc_layer,
    )

    output.add_live_msg(ms.gee.add_layer.format(ms.soc_layer))
    m.addLayer(model.soc.clip(geom).selfMask(), pm.viz_soc, ms.soc_layer)

    output.add_live_msg(ms.gee.add_layer.format(ms.ind_layer))
    m.addLayer(
        model.indicator_15_3_1.clip(geom).selfMask(),
        pm.viz_indicator,
        ms.ind_layer,
    )

    # add the aoi on the map
    empty = ee.Image().byte()

    aoi_line = empty.paint(
        **{"featureCollection": aoi_model.feature_collection, "color": 1, "width": 2}
    )
    m.addLayer(aoi_line, {"palette": v.theme.themes.dark.accent}, "aoi")
    output.add_live_msg(ms.map_loading_complete, "success")
    m.add_legend(
        legend_title=ms.map.legend.lc,
        legend_dict=model.lc_color,
        position="topleft",
    )

    return


def compute_indicator_maps(aoi_model, model, output):

    # raise an error if the years are not in the right order
    if not (model.start < model.end):
        raise Exception(ms.error.wrong_year)

    # compute intermediary maps
    vi_int, climate_int = integrate_ndvi_climate(aoi_model, model, output)
    model.productivity_trend = productivity_trajectory(
        model, vi_int, climate_int, output
    )
    model.productivity_performance = productivity_performance(
        aoi_model, model, vi_int, climate_int, output
    )
    model.productivity_state = productivity_state(aoi_model, model, vi_int, output)

    # compute result maps
    model.land_cover = land_cover(model, aoi_model, output)
    model.soc = soil_organic_carbon(model, aoi_model, output)
    if model.productivity_lookup_table == "GPGv2":
        model.productivity = productivity_final(
            model.productivity_trend,
            model.productivity_performance,
            model.productivity_state,
            output,
        )
    else:
        model.productivity = productivity_final_GPG1(
            model.productivity_trend,
            model.productivity_performance,
            model.productivity_state,
            output,
        )

    # sum up in a map
    model.indicator_15_3_1 = indicator_15_3_1(
        model.productivity, model.land_cover, model.soc, output
    )

    return


def compute_lc_transition_stats(aoi_model, model):
    """function to calculate the statistics of land cover transitions between two years to be used as input for the sankey diagram.
    input: ee.Image(land cover transition)
    retun: DataFrame.
    """
    landcover = model.land_cover.select("transition")
    scale = model.scale
    aoi = aoi_model.feature_collection.geometry().bounds()

    # make a list of all the possible transitions classes
    class_name = [
        i + "_" + j for i in model.lc_classlist_start for j in model.lc_classlist_end
    ]

    # creat a multi band image with all the classes as bands
    multiband_class = landcover.eq(model.lc_class_combination).rename(class_name)

    # calculate the area
    pixel_area = multiband_class.multiply(ee.Image.pixelArea().divide(10000))
    area_per_class = pixel_area.reduceRegion(
        **{
            "reducer": ee.Reducer.sum(),
            "geometry": aoi,
            "scale": scale,
            "maxPixels": 1e13,
            "bestEffort": True,
            "tileScale": 2,
        }
    )
    data = area_per_class.getInfo()

    # split the transition names and organise the data
    df = [[*[i for i in x.split("_")], y] for x, y in data.items()]

    # convert to a DataFrame
    df = pd.DataFrame(
        data=df, columns=[model.lc_year_start_esa, model.lc_year_end_esa, "Area"]
    )

    return df


def compute_stats_by_lc(aoi_model, model, select_landcover="end", indicator_name=None):
    """
    tabulate the area by land cover categories.
    input: ee.Image(ending land cover, final indicator)
    return: DataFrame

    """

    # land cover
    landcover = model.land_cover.select(select_landcover)

    # final indicator
    if indicator_name == "productivity sub-indicator":
        indicator = model.productivity
        variable = pm.degradation_class
    elif indicator_name == "soc sub-indicator":
        indicator = model.soc.select("soc")
        variable = pm.degradation_class
    elif indicator_name == "land cover sub-indicator":
        indicator = model.land_cover.select("degradation")
        variable = pm.degradation_class
    elif indicator_name == "productivity state":
        indicator = model.productivity_state.select("state_5_levels")
        variable = pm.prod_state_5_class
    elif indicator_name == "productivity trend":
        indicator = model.productivity_trend.select("trajectory_5_levels")
        variable = pm.prod_trend_5_class
    elif indicator_name == "productivity performance":
        indicator = model.productivity_performance
        variable = pm.prod_performance_class
    else:
        indicator = model.indicator_15_3_1
        variable = pm.degradation_class

    aoi = aoi_model.feature_collection.geometry().bounds()
    lc_name = model.lc_classlist_start
    lc_code = model.lc_codelist_start
    scale = model.scale

    # combine indicator and land cover together.
    # first digit represents the indicator, second two digits represents land cover categories
    lc_deg_combine = landcover.multiply(10).add(indicator)

    # all possible combined values
    class_value = [x * 10 + y for x in lc_code for y in variable.keys()]

    # all possible combined categories
    class_name = [x + "_" + y for x in lc_name for y in variable.values()]

    # creat a multi band image with all the categories as bands
    multiband_class = lc_deg_combine.eq(class_value).rename(class_name)

    # calculate the area
    pixel_area = multiband_class.multiply(ee.Image.pixelArea().divide(10000))
    area_per_class = pixel_area.reduceRegion(
        **{
            "reducer": ee.Reducer.sum(),
            "geometry": aoi,
            "scale": scale,
            "maxPixels": 1e13,
            "bestEffort": True,
            "tileScale": 2,
        }
    )
    data = area_per_class.getInfo()

    # split and organise the data
    df = [[*[i for i in x.split("_")], y] for x, y in data.items()]

    # convert to a DataFrame
    df = pd.DataFrame(data=df, columns=["Landcover", "Indicator", "Area"])

    return df


def compute_zonal_analysis(aoi_model, model, output):

    # create a result folder including the data parameters
    # create the aoi and parameter folder if not existing
    aoi_dir = pm.result_dir / su.normalize_str(aoi_model.name)
    result_dir = aoi_dir / model.folder_name()
    result_dir.mkdir(parents=True, exist_ok=True)

    indicator_stats = (
        result_dir / f"{aoi_model.name}_{model.folder_name()}_indicator_15_3_1"
    )

    # check if the file already exist
    indicator_zip = indicator_stats.with_suffix(".zip")
    if indicator_zip.is_file():
        output.add_live_msg(ms.download.already_exist.format(indicator_zip), "warning")
        return indicator_zip

    output_widget = Output()
    output.add_msg(output_widget)

    # to be removed when moving to shp
    indicator_csv = indicator_stats.with_suffix(".csv")
    scale = 100 if "Sentinel 2" in model.sensors else 300
    with output_widget:
        geemap.zonal_statistics_by_group(
            in_value_raster=model.indicator_15_3_1,
            in_zone_vector=aoi_model.feature_collection,
            out_file_path=indicator_csv,
            statistics_type="SUM",
            denominator=1000000,
            decimal_places=2,
            scale=scale,
            tile_scale=1.0,
        )
    # this should be removed once geemap is repaired
    #########################################################################
    aoi_json = geemap.ee_to_geojson(aoi_model.feature_collection)
    aoi_gdf = gpd.GeoDataFrame.from_features(aoi_json).set_crs("EPSG:4326")

    indicator_df = pd.read_csv(indicator_csv)
    if "Class_0" in indicator_df.columns:
        aoi_gdf["NoData"] = indicator_df["Class_0"]
    if "Class_3" in indicator_df.columns:
        aoi_gdf["Improve"] = indicator_df["Class_3"]
    if "Class_2" in indicator_df.columns:
        aoi_gdf["Stable"] = indicator_df["Class_2"]
    if "Class_1" in indicator_df.columns:
        aoi_gdf["Degrade"] = indicator_df["Class_1"]
    aoi_gdf = aoi_gdf[aoi_gdf.geom_type != "LineString"]
    aoi_gdf.to_file(indicator_stats.with_suffix(".shp"))
    #########################################################################

    # get all the shp extentions
    suffixes = [".dbf", ".prj", ".shp", ".cpg", ".shx"]  # , '.fix']

    # write the zip file
    with ZipFile(indicator_zip, "w") as myzip:
        for suffix in suffixes:
            file = indicator_stats.with_suffix(suffix)
            myzip.write(file, file.name)

    output.add_live_msg(ms.stats_complete.format(indicator_zip), "success")

    return indicator_zip


def indicator_15_3_1(productivity, landcover, soc, output):

    water = landcover.select("water")
    landcover = landcover.select("degradation")

    indicator = (
        ee.Image(0)
        .where(productivity.eq(3).And(landcover.eq(3)).And(soc.eq(3)), 3)
        .where(productivity.eq(3).And(landcover.eq(3)).And(soc.eq(2)), 3)
        .where(productivity.eq(3).And(landcover.eq(3)).And(soc.eq(1)), 1)
        .where(productivity.eq(3).And(landcover.eq(2)).And(soc.eq(3)), 3)
        .where(productivity.eq(3).And(landcover.eq(2)).And(soc.eq(2)), 3)
        .where(productivity.eq(3).And(landcover.eq(2)).And(soc.eq(1)), 1)
        .where(productivity.eq(3).And(landcover.eq(1)).And(soc.eq(3)), 1)
        .where(productivity.eq(3).And(landcover.eq(1)).And(soc.eq(2)), 1)
        .where(productivity.eq(3).And(landcover.eq(1)).And(soc.eq(1)), 1)
        .where(productivity.eq(2).And(landcover.eq(3)).And(soc.eq(3)), 3)
        .where(productivity.eq(2).And(landcover.eq(3)).And(soc.eq(2)), 3)
        .where(productivity.eq(2).And(landcover.eq(3)).And(soc.eq(1)), 1)
        .where(productivity.eq(2).And(landcover.eq(2)).And(soc.eq(3)), 3)
        .where(productivity.eq(2).And(landcover.eq(2)).And(soc.eq(2)), 2)
        .where(productivity.eq(2).And(landcover.eq(2)).And(soc.eq(1)), 1)
        .where(productivity.eq(2).And(landcover.eq(1)).And(soc.eq(3)), 1)
        .where(productivity.eq(2).And(landcover.eq(1)).And(soc.eq(2)), 1)
        .where(productivity.eq(2).And(landcover.eq(1)).And(soc.eq(1)), 1)
        .where(productivity.eq(1).And(landcover.eq(3)).And(soc.eq(3)), 1)
        .where(productivity.eq(1).And(landcover.eq(3)).And(soc.eq(2)), 1)
        .where(productivity.eq(1).And(landcover.eq(3)).And(soc.eq(1)), 1)
        .where(productivity.eq(1).And(landcover.eq(2)).And(soc.eq(3)), 1)
        .where(productivity.eq(1).And(landcover.eq(2)).And(soc.eq(2)), 1)
        .where(productivity.eq(1).And(landcover.eq(2)).And(soc.eq(1)), 1)
        .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(3)), 1)
        .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(2)), 1)
        .where(productivity.eq(1).And(landcover.eq(1)).And(soc.eq(1)), 1)
        .where(productivity.eq(1).And(landcover.lt(1)).And(soc.lt(1)), 1)
        .where(productivity.lt(1).And(landcover.eq(1)).And(soc.lt(1)), 1)
        .where(productivity.lt(1).And(landcover.lt(1)).And(soc.eq(1)), 1)
        .updateMask(water)
    )

    return indicator.uint8()


def custom_lc_values(land_cover):
    image = ee.Image(land_cover)
    geometry = image.geometry()
    reduction = image.reduceRegion(
        ee.Reducer.frequencyHistogram(), geometry, bestEffort=True
    )
    values = ee.Dictionary(reduction.get(image.bandNames().get(0))).keys().getInfo()
    return [int(v) for v in values]
