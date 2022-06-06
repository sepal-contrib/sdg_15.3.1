import ipyvuetify as v

from component.message import ms

vegetation_index = [
    {"text": ms.vi.ndvi, "value": "ndvi", "disabled": False},
    {"text": ms.vi.evi, "value": "evi", "disabled": False},
    {"text": ms.vi.msvi, "value": "msvi", "disabled": False},
]

lceu = [
    {
        "text": ms.lceu.gaes,
        "value": "gaes",
        "disabled": False,
    },
    {"text": ms.lceu.aez, "value": "aez", "disabled": False},
    {"text": ms.lceu.wte, "value": "wte", "disabled": False},
    {
        "text": ms.lceu.hru,
        "value": "hru",
        "disabled": False,
    },
    {"text": ms.lceu.calculate, "value": "calculate", "disabled": False},
]

productivity_lookup_table = [
    {"text": ms.productivity_lookuptable.gpgv2, "value": "GPGv2"},
    {"text": ms.productivity_lookuptable.gpgv1, "value": "GPGv1"},
]

trajectories = [
    {"text": ms.trend.ndvi, "value": "ndvi_trend", "disabled": False},
    {"text": ms.trend.p_res, "value": "p_res_trend", "disabled": False},
    {"text": ms.trend.s_res, "value": "s_res_trend", "disabled": True},
    {"text": ms.trend.ue, "value": "ue_trend", "disabled": False},
]

jrc_seasonality_tick = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

climate_regimes = [
    {"text": ms.clim_regim.temp_dry, "value": 0.80},
    {"text": ms.clim_regim.temp_moist, "value": 0.69},
    {"text": ms.clim_regim.trop_dry, "value": 0.58},
    {"text": ms.clim_regim.trop_moist, "value": 0.48},
    {"text": ms.clim_regim.trop_mont, "value": 0.64},
]

legend = {
    ms.legend.degraded: "#d7191c",
    ms.legend.stable: "#ffffbf",
    ms.legend.improved: "#2c7bb6",
}

legend_bar = {
    ms.legend.degraded: "#d7191c",
    ms.legend.stable: "#ffffbf",
    ms.legend.improved: "#2c7bb6",
    ms.legend.nodata: "#9ea7ad",
}
lc_color = {
    ms.classes.forest: "#02A000",
    ms.classes.grassland: "#FFB432",
    ms.classes.cropland: "#FFFF64",
    ms.classes.wetland: "#04DC83",
    ms.classes.artificial: "#C31400",
    ms.classes.bareland: "#FFF5D7",
    ms.classes.water: "#0046C8",
}


viz_prod = {"max": 3, "min": 1, "palette": list(legend.values())}
viz_lc_sub = {"max": 3, "min": 1, "palette": list(legend.values())}
viz_soc = {"max": 3, "min": 1, "palette": list(legend.values())}
viz_indicator = {"max": 3, "min": 1, "palette": list(legend.values())}
