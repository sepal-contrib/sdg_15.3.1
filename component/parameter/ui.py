import ipyvuetify as v

from component.message import ms 

trajectories = [
    {'text': ms._15_3_1.trend.ndvi, 'value': 'ndvi_trend', 'disabled': False},
    {'text': ms._15_3_1.trend.p_res, 'value': 'p_restrend', 'disabled': False},
    {'text': ms._15_3_1.trend.s_res, 'value': 's_restrend', 'disabled': True},
    {'text': ms._15_3_1.trend.ue, 'value': 'ue_trend',   'disabled': False}
]

climate_regimes = [
    {'text': ms._15_3_1.clim_regim.temp_dry,    'value': 0.80},
    {'text': ms._15_3_1.clim_regim.temp_moist, 'value': 0.69},
    {'text': ms._15_3_1.clim_regim.trop_dry,    'value': 0.58},
    {'text': ms._15_3_1.clim_regim.trop_moist,  'value': 0.48},
    {'text': ms._15_3_1.clim_regim.trop_mont,'value': 0.64}
]

legend = {
    ms._15_3_1.legend.degraded : v.theme.themes.dark.error,
    ms._15_3_1.legend.stable : v.theme.themes.dark.primary,
    ms._15_3_1.legend.improved : v.theme.themes.dark.success
}

viz_prod      = {"max": 3, "min":1, "palette": list(legend.values())}
viz_lc        = {"max": 3, "min":1, "palette": list(legend.values())}
viz_soc       = {"max": 3, "min":1, "palette": list(legend.values())}
viz_indicator = {"max": 3, "min":1, "palette": list(legend.values())}

