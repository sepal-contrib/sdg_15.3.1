import ipyvuetify as v

trajectories = [
    {'text': 'ndvi_trend', 'value': 'ndvi_trend', 'disabled': False},
    {'text': 'p_restrend', 'value': 'p_restrend', 'disabled': False},
    {'text': 's_restrend', 'value': 's_restrend', 'disabled': True},
    {'text': 'ue_trend',   'value': 'ue_trend',   'disabled': False}
]

climate_regimes = [
    {'text': 'Temperate dry (coef = 0.8)',    'value': 0.80},
    {'text': 'Temperate moist (coef = 0.69)', 'value': 0.69},
    {'text': 'Tropical dry (coef = 0.58)',    'value': 0.58},
    {'text': 'Tropical moist (coef = 0.48)',  'value': 0.48},
    {'text': 'Tropical montane (coef = 0.64)','value': 0.64}
]
legend = {
    '<b>productivity</b> degraded': v.theme.themes.dark.error,
    '<b>productivity</b> stable'  : v.theme.themes.dark.primary,
    '<b>productivity</b> improved': v.theme.themes.dark.success,
    '<b>land cover</b> degraded'  : v.theme.themes.dark.error,
    '<b>land cover</b> stable'    : v.theme.themes.dark.primary,
    '<b>land cover</b> improved'  : v.theme.themes.dark.success,
    '<b>soc</b> degraded'         : v.theme.themes.dark.error,
    '<b>soc</b> stable'           : v.theme.themes.dark.primary,
    '<b>soc</b> improved'         : v.theme.themes.dark.success,
    '<b>indicator</b> degraded'   : v.theme.themes.dark.error,
    '<b>indicator</b> stable'     : v.theme.themes.dark.primary,
    '<b>indicator</b> improved'   : v.theme.themes.dark.success,
}

legend_test = {
    'degraded' : v.theme.themes.dark.error,
    'stable'   : v.theme.themes.dark.primary,
    'improved' : v.theme.themes.dark.success
}

viz_prod      = {"palette": list(legend.values())[:3]}
viz_lc        = {"max": 3, "min":1, "palette": list(legend.values())[3:6]}
viz_soc       = {"max": 3, "min":1, "palette": list(legend.values())[6:9]}
viz_indicator = {"max": 3, "min":1, "palette": list(legend.values())[9:12]}

