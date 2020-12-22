from sepal_ui import sepalwidgets as sw
from sepal_ui import mapping as sm
from sepal_ui.scripts import utils as su
import ipyvuetify as v
from datetime import datetime

from scripts import parameter as pm
from scripts import run

class TileIo():
    
    def __init__(self):
        
        # times
        self.start = None
        self.target_start = None
        self.end = None
        
        # sensors
        self.sensors = None
        
        # trajectory 
        self.trajectory = None
        
        # matrix, change output format to a plain list. we need it to remap the land cover instead of a matrix.
        self.transition_matrix = [[0 for i in range(7)] for i in range(7)]
        
        #Climate regime
        self.conversion_coef =None
        
class ClimateRegime(v.Col):
    
    REGIMES = [
        'Per pixel based  on global climate data', 
        'Use predefined climate regime',
        'Use custom value'
    ]
    
    def __init__(self, io, output):
        
        self.io = io
        self.output = output
        
        # create the widgets 
        self.type_select = v.Select(label = 'Climate regime options', items = self.REGIMES, v_model=self.REGIMES[0])
        
        self.climate_regimes = v.Select(label = 'Climate regime', items = pm.climate_regimes, v_model=None)
        output.bind(self.climate_regimes, io, 'conversion_coef')
        
        self.custom_regime = v.Slider(label = 'Custom climate regime value', max = 1, step = .01, v_model = None)
        output.bind(self.custom_regime, io, 'conversion_coef')
        
        # hide the components 
        self._reset()        
        
        # create the layout 
        super().__init__(xs12=True, class_='mt-5', children = [self.type_select, self.climate_regimes, self.custom_regime])
        
        # add some binding
        self.type_select.observe(self._update_selection, 'v_model')
        
    def _update_selection(self, change):
        
        # reset the variables 
        self._reset()
        
        if change['new'] == self.REGIMES[1]: # specify
            su.show_component(self.climate_regimes)
        elif change['new'] == self.REGIMES[2]: # custom 
            su.show_component(self.custom_regime)
            
        return
    
    def _reset(self):
        
        # remove values 
        self.climate_regimes.v_model = None
        self.custom_regime.v_model = None
        
        # hide components
        su.hide_component(self.climate_regimes)
        su.hide_component(self.custom_regime)
        
        return
        
class PickerLine(v.Layout):
    
    YEAR_RANGE = [y for y in range(pm.land_use_max_year, pm.L4_start - 1, -1)]
    
    def __init__(self, io, output):
        
        self.io = io
        self.output = output
        
        self.start_picker = v.Select(label='Start year', items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        output.bind(self.start_picker, io, 'start')
        
        target_picker = v.Select(label='Start year of the target period', items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        output.bind(target_picker, io, 'target_start')
        
        end_picker = v.Select(label='End year', items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        output.bind(end_picker, io, 'end')
        
        super().__init__(xs=12, row=True,  children=[self.start_picker, target_picker, end_picker])
        
class MatrixInput(v.Html):
    
    VALUES = {
        '+': (1, v.theme.themes.dark.success),  
        '': (0, v.theme.themes.dark.primary),
        '-': (-1, v.theme.themes.dark.error)
    }
    
    def __init__(self, line, column, io, output):
        
        # get the io for dynamic modification
        self.io = io
        
        # get the line and column of the td in the matrix
        self.column = column
        self.line = line
        
        # get the output
        self.output = output
        
        self.val = v.Select(dense = True, color = 'white', items = [*self.VALUES], class_='ma-1', v_model = 0)
        
        super().__init__(
            style_ = f'background-color: {v.theme.themes.dark.primary}',
            tag = 'td',
            children = [self.val]
        )
        
        # connect the color to the value
        self.val.observe(self.color_change, 'v_model')
        
    def color_change(self, change):            
        
        val, color = self.VALUES[change['new']]
        
        self.style_ = f'background-color: {color}'
        self.io.transition_matrix[self.line][self.column] = val
        
        self.output.add_msg('You have changed your transition matrix')
            
        return 
        
class TransitionMatrix(v.SimpleTable):
    
    CLASSES = ['Forest', 'Grassland', 'Cropland', 'Wetland', 'Artificial area', 'Bare land', 'water body']
    
    def __init__(self, io, output):
        
        # create a header 
        header = [v.Html(tag = 'tr', children = [v.Html(tag = 'th', children = [''])] + [v.Html(tag = 'th', children = [class_]) for class_ in self.CLASSES])]
        
        # create a row
        rows = []
        for i, baseline in enumerate(self.CLASSES):
            
            inputs = []
            for j, target in enumerate(self.CLASSES):
                matrix_input = MatrixInput(i, j, io, output)
                
                input_ = v.Html(tag='td', class_='ma-0 pa-0', children=[matrix_input])
                inputs.append(input_)
                
            row = v.Html(tag='tr', children=(
                [v.Html(tag='th', children=[baseline])] 
                + inputs
            ))
            rows.append(row)
                   
                   
            
        # create the simple table 
        super().__init__(
            children = [
                v.Html(tag = 'tbody', children = header + rows)
            ]
        )
        
    def get_td(self, val):
        
        # degradation
        if val == self.VAlUES[2]: 
            color = v.theme.themes.dark.error
        # stable
        elif val == self.VAlUES[1]:
            color = v.theme.themes.dark.primary
        # Improvement
        elif val == self.VAlUES[0]:
            color = v.theme.themes.dark.success
        
        td = v.Html(tag='td', style_=f'background-color: {color}', children=[str(val)])
        
        return td
    
class SensorSelect(v.Select):
    
    def __init__(self, **kwargs):
        
        super().__init__(**kwargs)
        
    def update_sensors(self, change):
        
        # deselect all 
        self.v_model = None
        
        # define the offset that should be used based on the yearr in the sensors list
        if change['new'] >= 2015: # launch of Sentinel 2
            last_sat = 5
        elif change['new'] >= 2013: # launch of Landsat 8
            last_sat = 4
        elif change['new'] >= 1999: #launch of landsat 7
            last_sat = 3
        elif change['new'] >= 1984: #launch of landsat 5
            last_sat = 2
        else:
            last_sat = 1
            
        self.items = [*pm.sensors][:last_sat]
            
        
class Tile_15_3_1(sw.Tile):
    
    def __init__(self, aoi_io, result_tile):
        
        # use io 
        self.aoi_io = aoi_io
        self.io = TileIo()
        
        # output
        self.output = sw.Alert()
        
        #result tile
        self.result_tile = result_tile
        
        markdown = sw.Markdown('Some explainations should go here')
        
        pickers = PickerLine(self.io, self.output)
        
        self.sensor_select = SensorSelect(items=[], label="select sensor", multiple=True, v_model=None)
        self.output.bind(self.sensor_select, self.io, 'sensors')
        
        trajectory = v.Select(label='trajectory', items=pm.trajectories, v_model=None)
        self.output.bind(trajectory, self.io, 'trajectory')
        
        transition_label = v.Html(class_='grey--text mt-2', tag='h3', children=['Transition matrix'])
        
        transition_matrix = TransitionMatrix(self.io, self.output)
        
        climate_regime = ClimateRegime(self.io, self.output)
        
        btn = sw.Btn(class_='mt-5')
        
        super().__init__(
            self.result_tile._metadata['mount_id'],
            '15.3.1 Proportion of degraded land over total land area',
            inputs = [markdown, pickers, self.sensor_select, trajectory, transition_label, transition_matrix, climate_regime],
            btn = btn,
            output = self.output
        )
        
        btn.on_event('click', self.start_process)
        pickers.start_picker.observe(self.sensor_select.update_sensors, 'v_model')
        
        
    def start_process(self, widget, data, event):
        
        widget.toggle_loading()
        
        land_cover = run.land_cover(self.io, self.aoi_io, self.output)

        soc = run.soil_organic_carbon(self.io, self.aoi_io, self.output)
        
        ndvi_int, climate_int = run.integrate_ndvi_climate(self.aoi_io, self.io, self.output)
        
        productivity_trajectory = run.productivity_trajectory(self.io, ndvi_int, climate_int, self.output)
        productivity_performance = run.productivity_performance(self.io_aoi, self.io, ndvi_int, climate_int, self.output)
        productivity_state = run.productivity_state(self.io_aoi, self.io, ndvi_int, climate_int, self.output)
                                                                
        productivity = productivity_final(productivity_trajectory, productivity_performance, productivity_state, self.output)

        indicator_15_3_1 = indicator_15_3_1(productivity, land_cover, soc, self.output)


        # create a map 
        m = sm.SepalMap()
        m.zoom_ee_object(self.aoi_io.get_aoi_ee().geometry())
        
        # add the layers 
        m.addLayer(productivity, pm.viz, 'productivity')
        m.addLayer(land_cover, pm.viz, 'land_cover')
        m.addLayer(soc, pm.viz, 'soil_organic_carbon')
        m.addLayer(indicator_15_3_1, pm.viz, 'indicator_15_3_1')
        
        # add the map to the result tile 
        self.result_tile.set_content([m])
        
        widget.toggle_loading()
            
        return 
