import ipyvuetify as v

from component.message import cm

vegetation_index = [
    {"text": cm.vi.ndvi, "value": "ndvi", "disabled": False},
    {"text": cm.vi.evi, "value": "evi", "disabled": False},
    {"text": cm.vi.msvi, "value": "msvi", "disabled": False},
]

lceu = [
    {
        "text": cm.lceu.gaes,
        "value": "gaes",
        "disabled": False,
    },
    {"text": cm.lceu.aez, "value": "aez", "disabled": False},
    {"text": cm.lceu.wte, "value": "wte", "disabled": False},
    {
        "text": cm.lceu.hru,
        "value": "hru",
        "disabled": False,
    },
    {"text": cm.lceu.calculate, "value": "calculate", "disabled": False},
]

productivity_lookup_table = [
    {"text": cm.productivity_lookuptable.gpgv2, "value": "GPGv2"},
    {"text": cm.productivity_lookuptable.gpgv1, "value": "GPGv1"},
]

trajectories = [
    {"text": cm.trend.ndvi, "value": "ndvi_trend", "disabled": False},
    {"text": cm.trend.p_res, "value": "p_res_trend", "disabled": False},
    {"text": cm.trend.s_res, "value": "s_res_trend", "disabled": True},
    {"text": cm.trend.ue, "value": "ue_trend", "disabled": False},
]

jrc_seasonality_tick = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

climate_regimes = [
    {"text": cm.clim_regim.temp_dry, "value": 0.80},
    {"text": cm.clim_regim.temp_moist, "value": 0.69},
    {"text": cm.clim_regim.trop_dry, "value": 0.58},
    {"text": cm.clim_regim.trop_moist, "value": 0.48},
    {"text": cm.clim_regim.trop_mont, "value": 0.64},
]

legend = {
    cm.legend.degraded: "#d7191c",
    cm.legend.stable: "#ffffbf",
    cm.legend.improved: "#2c7bb6",
}

legend_bar = {
    cm.legend.degraded: "#d7191c",
    cm.legend.stable: "#ffffbf",
    cm.legend.improved: "#2c7bb6",
    cm.legend.nodata: "#9ea7ad",
}
lc_color = {
    cm.classes.forest: "#02A000",
    cm.classes.grassland: "#FFB432",
    cm.classes.cropland: "#FFFF64",
    cm.classes.wetland: "#04DC83",
    cm.classes.artificial: "#C31400",
    cm.classes.bareland: "#FFF5D7",
    cm.classes.water: "#0046C8",
}


viz_prod = {"max": 3, "min": 1, "palette": list(legend.values())}
viz_lc_sub = {"max": 3, "min": 1, "palette": list(legend.values())}
viz_soc = {"max": 3, "min": 1, "palette": list(legend.values())}
viz_indicator = {"max": 3, "min": 1, "palette": list(legend.values())}
