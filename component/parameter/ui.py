import ipyvuetify as v

from component.message import ms 

vegetation_index = [
        {'text':ms._15_3_1.vi.ndvi, 'value':'ndvi'},
        {'text':ms._15_3_1.vi.evi, 'value':'evi'},
        {'text':ms._15_3_1.vi.msvi, 'value':'msvi'}      
]


lceu = [
        {'text':ms._15_3_1.lceu.calculate, 'value':'calculate', 'disabled': False},
        {'text':ms._15_3_1.lceu.wte, 'value':'World Ecosystems', 'disabled': False},
        {'text':ms._15_3_1.lceu.hru, 'value':'Global Homogeneous Response Units', 'disabled': True},
        {'text':ms._15_3_1.lceu.gaes, 'value':'Global Agro-Environmental Stratification', 'disabled': True}
]


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
# v.theme.themes.dark.error
# v.theme.themes.dark.primary
# v.theme.themes.dark.success
legend = {
    ms._15_3_1.legend.degraded :'#F28482',
    ms._15_3_1.legend.stable :'#D5B9B2',
    ms._15_3_1.legend.improved : '#4F772D' 
}

lc_color = {'Tree-covered':'yellowgreen', 'Grassland':'palegreen', 'Cropland':'gold', 'Wetland':'turquoise', 'Artificial':'gainsboro', 'Other land':'floralwhite', 'Water body':'dodgerblue'}

viz_lc        = {"max": 7, "min":1, "palette": list(lc_color.values())}
viz_prod      = {"max": 3, "min":1, "palette": list(legend.values())}
viz_lc_sub    = {"max": 3, "min":1, "palette": list(legend.values())}
viz_soc       = {"max": 3, "min":1, "palette": list(legend.values())}
viz_indicator = {"max": 3, "min":1, "palette": list(legend.values())}

