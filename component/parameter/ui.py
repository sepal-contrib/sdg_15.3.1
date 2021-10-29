import ipyvuetify as v

from component.message import ms

vegetation_index = [
    {"text": ms._15_3_1.vi.ndvi, "value": "ndvi"},
    {"text": ms._15_3_1.vi.evi, "value": "evi"},
    {"text": ms._15_3_1.vi.msvi, "value": "msvi"},
]

lceu = [
    {"text": ms._15_3_1.lceu.calculate, "value": "calculate", "disabled": False},
    {"text": ms._15_3_1.lceu.wte, "value": "wte", "disabled": False},
    {
        "text": ms._15_3_1.lceu.hru,
        "value": "hru",
        "disabled": True,
    },
    {
        "text": ms._15_3_1.lceu.gaes,
        "value": "gaes",
        "disabled": True,
    },
]

trajectories = [
    {"text": ms._15_3_1.trend.ndvi, "value": "ndvi_trend", "disabled": False},
    {"text": ms._15_3_1.trend.p_res, "value": "p_res_trend", "disabled": False},
    {"text": ms._15_3_1.trend.s_res, "value": "s_res_trend", "disabled": True},
    {"text": ms._15_3_1.trend.ue, "value": "ue_trend", "disabled": False},
]

climate_regimes = [
    {"text": ms._15_3_1.clim_regim.temp_dry, "value": 0.80},
    {"text": ms._15_3_1.clim_regim.temp_moist, "value": 0.69},
    {"text": ms._15_3_1.clim_regim.trop_dry, "value": 0.58},
    {"text": ms._15_3_1.clim_regim.trop_moist, "value": 0.48},
    {"text": ms._15_3_1.clim_regim.trop_mont, "value": 0.64},
]

legend = {
    ms._15_3_1.legend.degraded: "#d7191c",
    ms._15_3_1.legend.stable: "#ffffbf",
    ms._15_3_1.legend.improved: "#2c7bb6",
}

lc_color = {
    ms._15_3_1.classes.forest: "#02A000",
    ms._15_3_1.classes.grassland: "#FFB432",
    ms._15_3_1.classes.cropland: "#FFFF64",
    ms._15_3_1.classes.wetland: "#04DC83",
    ms._15_3_1.classes.artificial: "#C31400",
    ms._15_3_1.classes.bareland: "#FFF5D7",
    ms._15_3_1.classes.water: "#0046C8",
}

viz_lc = {"max": 7, "min": 1, "palette": list(lc_color.values())}
viz_prod = {"max": 3, "min": 1, "palette": list(legend.values())}
viz_lc_sub = {"max": 3, "min": 1, "palette": list(legend.values())}
viz_soc = {"max": 3, "min": 1, "palette": list(legend.values())}
viz_indicator = {"max": 3, "min": 1, "palette": list(legend.values())}
