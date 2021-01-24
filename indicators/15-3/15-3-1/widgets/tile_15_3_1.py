from pathlib import Path
from datetime import datetime

from sepal_ui import sepalwidgets as sw
from sepal_ui import mapping as sm
from sepal_ui.scripts import utils as su
import ipyvuetify as v
import geemap
import ee 
from ipywidgets import Output, Layout

from scripts import parameter as pm
from scripts import run

ee.Initialize()

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
        self.transition_matrix = pm.default_trans_matrix
        
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
        
        # create the widgets
        self.start_picker = v.Select(label='Start year', items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        self.target_picker = v.Select(label='Start year of the target period', items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        self.end_picker = v.Select(label='End year', items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        
        # bind them to the output
        output = output \
            .bind(self.start_picker, io, 'start') \
            .bind(self.target_picker, io, 'target_start') \
            .bind(self.end_picker, io, 'end')
        
        super().__init__(xs=12, row=True,  children=[self.start_picker, self.target_picker, self.end_picker])
        
class MatrixInput(v.Html):
    
    VALUES = {
        '+': (1, v.theme.themes.dark.success),  
        '': (0, v.theme.themes.dark.primary),
        '-': (-1, v.theme.themes.dark.error)
    }
    
    
    
    def __init__(self, line, column, io, default_value, output):
        
        # get the io for dynamic modification
        self.io = io
        
        # get the line and column of the td in the matrix
        self.column = column
        self.line = line
        
        # get the output
        self.output = output
        
        self.val = v.Select(dense = True, color = 'white', items = [*self.VALUES], class_='ma-1', v_model = default_value)
        
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
    
    DECODE = {1: '+', 0: '', -1:'-'}
    
    def __init__(self, io, output):
        
        # create a header 
        header = [v.Html(tag = 'tr', children = [v.Html(tag = 'th', children = [''])] + [v.Html(tag = 'th', children = [class_]) for class_ in self.CLASSES])]
        
        # create a row
        rows = []
        for i, baseline in enumerate(self.CLASSES):
            
            inputs = []
            for j, target in enumerate(self.CLASSES):
                # create a input with default matrix value
                default_value = self.DECODE[pm.default_trans_matrix[i][j]]
                matrix_input = MatrixInput(i, j, io, default_value, output)
                matrix_input.color_change({'new': default_value})
                
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
        
        # define the offset that should be used based on the year in the sensors list
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
        
        # change senso items 
        self.items = [*pm.sensors][:last_sat]
        
        # select them all by default 
        self.v_model = [*pm.sensors][:last_sat]
        
        return
        
class Tile_15_3_1(sw.Tile):
    
    def __init__(self, aoi_io, result_tile):
        
        # use io 
        self.aoi_io = aoi_io
        self.io = TileIo()
        
        # output
        self.output = sw.Alert()
        
        #result tile
        self.result_tile = result_tile
        
        # create the widgets that will be displayed
        markdown = sw.Markdown('Some explainations should go here')
        pickers = PickerLine(self.io, self.output)
        self.sensor_select = SensorSelect(items=[], label="select sensor", multiple=True, v_model=None, chips=True)
        trajectory = v.Select(label='trajectory', items=pm.trajectories, v_model=None)
        transition_label = v.Html(class_='grey--text mt-2', tag='h3', children=['Transition matrix'])
        transition_matrix = TransitionMatrix(self.io, self.output)
        climate_regime = ClimateRegime(self.io, self.output)
        
        # bind the standars widgets to variables 
        self.output \
            .bind(self.sensor_select, self.io, 'sensors') \
            .bind(trajectory, self.io, 'trajectory')
        
        # 
        self.btn = sw.Btn(class_='mt-5')
        
        # create the actual tile
        super().__init__(
            self.result_tile._metadata['mount_id'],
            '15.3.1 Proportion of degraded land over total land area',
            inputs = [
                markdown, 
                pickers, 
                self.sensor_select, 
                trajectory, 
                transition_label, 
                transition_matrix, 
                climate_regime
            ],
            btn = self.btn,
            output = self.output
        )
        
        # add links between the widgets
        self.btn.on_event('click', self.start_process)
        pickers.end_picker.observe(self.sensor_select.update_sensors, 'v_model')
        
        # clear the alert 
        self.output.reset()
        
        
    def start_process(self, widget, data, event):
        
        widget.toggle_loading()
        
        # check the inputs 
        
        
        #try 
        
        # compute intermediary maps 
        ndvi_int, climate_int = run.integrate_ndvi_climate(self.aoi_io, self.io, self.output)
        productivity_trajectory = run.productivity_trajectory(self.io, ndvi_int, climate_int, self.output)
        productivity_performance = run.productivity_performance(self.aoi_io, self.io, ndvi_int, climate_int, self.output)
        productivity_state = run.productivity_state(self.aoi_io, self.io, ndvi_int, climate_int, self.output) 
        
        # compute result maps 
        land_cover = run.land_cover(self.io, self.aoi_io, self.output)
        soc = run.soil_organic_carbon(self.io, self.aoi_io, self.output)
        productivity = run.productivity_final(productivity_trajectory, productivity_performance, productivity_state, self.output)
        
        # sump up in a map
        indicator_15_3_1 = run.indicator_15_3_1(productivity, land_cover, soc, self.output)

        # create the csv result
        indicator_15_3_1_stats = Path('~', 'downloads', f'{self.aoi_io.get_aoi_name()}_indicator_15_3_1.csv').expanduser()
        
        output_widget = Output()
        self.output.add_msg(output_widget)
        
        with output_widget:
            geemap.zonal_statistics_by_group(
                in_value_raster = indicator_15_3_1,
                in_zone_vector = self.aoi_io.get_aoi_ee(),
                out_file_path = indicator_15_3_1_stats,
                statistics_type = "PERCENTAGE",
                decimal_places=2,
                tile_scale=1.0
            )
        self.result_tile.csv_btn.set_url(str(indicator_15_3_1_stats))

        # get the result map 
        m = self.result_tile.m
        m.zoom_ee_object(self.aoi_io.get_aoi_ee().geometry())
        
        # add the layers 
        geom = self.aoi_io.get_aoi_ee().geometry().bounds()
        m.addLayer(productivity.clip(geom), pm.viz, 'productivity')
        m.addLayer(land_cover.select('degredation').clip(geom), pm.viz, 'land_cover')
        m.addLayer(soc.clip(geom), pm.viz, 'soil_organic_carbon')
        m.addLayer(indicator_15_3_1.clip(geom), pm.viz, 'indicator_15_3_1')
        
        # add the aoi on the map 
        m.addLayer(self.aoi_io.get_aoi_ee(), {'color': v.theme.themes.dark.info}, 'aoi')
        
        #except Exception as e:
        #    self.output.add_live_msg(e, 'error')
        
        widget.toggle_loading()
            
        return 
    
class Result_15_3_1(sw.Tile):
    
    def __init__(self, aoi_io, **kwargs):
        
        # create an output for the downloading method
        self.output = sw.Alert()
        
        # get io for the downloading 
        self.aoi_io = aoi_io
        
        # create the result map
        self.m = sm.SepalMap()
        
        # add a download btn for csv and a download btn for the sepal
        self.csv_btn = sw.DownloadBtn('Downlad stats in .csv')
        
        self.tif_btn = sw.Btn(text = 'Download maps as .tif in sepal',icon = 'mdi-download')
        self.tif_btn.color = 'success'
        self.tif_btn.disabled = True
        self.tif_btn.class_ = 'ma-2'
        
        # aggregate the btn as a line 
        btn_line =  v.Layout(Row=True, children=[self.csv_btn, self.tif_btn])
        
        # init the tile 
        super().__init__(
            '15_3_1_widgets', 
            'Results', 
            [btn_line, self.m],
            output = self.output
        )
        
        # link the downlad as tif to a function
        
        
        
        
        