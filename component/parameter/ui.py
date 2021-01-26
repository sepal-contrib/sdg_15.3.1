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

viz_prod = {"max": 1, "min":-1, "palette": ['#e9a3c9', '#ffffbf', '#a1d76a']}
viz_lc = {"max": 1, "min":-1, "palette": ['#d8b365', '#d8b365', '#5ab4ac']}
viz_soc = {"max": 1, "min":-1, "palette": ['#ef8a62', '#ffffff', '#999999']}
viz_indicator = {"max": 1, "min":-1, "palette": ['#fc8d59', '#ffffbf', '#91cf60']}

legend = {
    '<b>productivity</b> degraded': '#e9a3c9',
    '<b>productivity</b> stable': '#ffffbf',
    '<b>productivity</b> improved': '#a1d76a',
    '<b>land cover</b> degraded': '#d8b365',
    '<b>land cover</b> stable': '#d8b365',
    '<b>land cover</b> improved': '#5ab4ac',
    '<b>soc</b> degraded': '#ef8a62',
    '<b>soc</b> stable': '#ffffff',
    '<b>soc</b> improved': '#999999',
    '<b>indicator</b> degraded': '#fc8d59',
    '<b>indicator</b> stable': '#ffffbf',
    '<b>indicator</b> improved': '#91cf60',
}