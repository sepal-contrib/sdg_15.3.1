from pathlib import Path
from datetime import datetime
import time

from sepal_ui import sepalwidgets as sw
from sepal_ui import mapping as sm
from sepal_ui.scripts import utils as su
import ipyvuetify as v
import geemap
import ee 
from ipywidgets import Output, Layout
import rasterio as rio
from rasterio.merge import merge

from scripts import parameter as pm
from scripts import run
from scripts import gdrive
from scripts import utils

ee.Initialize()

class Io_15_3_1():
    
    def __init__(self):
        
        #####################
        ##      input      ##
        #####################
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
        
        ######################
        ##      output      ##
        ######################
        
        self.land_cover = None
        self.soc = None
        self.productivity = None
        self.indicator_15_3_1 = None
        
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
    
    def __init__(self, aoi_io, io, result_tile):
        
        # use io 
        self.aoi_io = aoi_io
        self.io = io
        
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
        self.io.land_cover = run.land_cover(self.io, self.aoi_io, self.output)
        self.io.soc = run.soil_organic_carbon(self.io, self.aoi_io, self.output)
        self.io.productivity = run.productivity_final(productivity_trajectory, productivity_performance, productivity_state, self.output)
        
        # sump up in a map
        self.io.indicator_15_3_1 = run.indicator_15_3_1(self.io.productivity, self.io.land_cover, self.io.soc, self.output)

        # create the csv result
        indicator_15_3_1_stats = pm.result_dir.joinpath(f'{self.aoi_io.get_aoi_name()}_indicator_15_3_1.csv')
        
        output_widget = Output()
        self.output.add_msg(output_widget)
        
        with output_widget:
            geemap.zonal_statistics_by_group(
                in_value_raster = self.io.indicator_15_3_1,
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
        m.addLayer(self.io.productivity.clip(geom), pm.viz, 'productivity')
        m.addLayer(self.io.land_cover.select('degredation').clip(geom), pm.viz, 'land_cover')
        m.addLayer(self.io.soc.clip(geom), pm.viz, 'soil_organic_carbon')
        m.addLayer(self.io.indicator_15_3_1.clip(geom), pm.viz, 'indicator_15_3_1')
        
        # add the aoi on the map 
        m.addLayer(self.aoi_io.get_aoi_ee(), {'color': v.theme.themes.dark.info}, 'aoi')
        
        # release the download btn
        self.result_tile.tif_btn.disabled = False
        
        #except Exception as e:
        #    self.output.add_live_msg(e, 'error')
        
        widget.toggle_loading()
            
        return 
    
class Result_15_3_1(sw.Tile):
    
    def __init__(self, aoi_io, io, **kwargs):
        
        # create an output for the downloading method
        self.output = sw.Alert()
        
        # get io for the downloading 
        self.aoi_io = aoi_io
        self.io = io
        
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
        self.tif_btn.on_event('click', self.download_maps)
        
        
    def download_maps(self, widget, event, data):
        
        widget.toggle_loading()
            
        # get the export scale 
        scale = 10 if 'Sentinel 2' in self.io.sensors else 30
        
        # create the export path
        land_cover_desc = f'{self.aoi_io.get_aoi_name()}_land_cover'
        soc_desc = f'{self.aoi_io.get_aoi_name()}_soc'
        productivity_desc = f'{self.aoi_io.get_aoi_name()}_productivity'
        indicator_15_3_1_desc = f'{self.aoi_io.get_aoi_name()}_indicator_15_3_1'
        
        # load the drive_handler
        drive_handler = gdrive.gdrive()
        
        # download all files
        downloads = drive_handler.download_to_disk(land_cover_desc, self.io.land_cover, self.aoi_io, self.output)
        downloads = drive_handler.download_to_disk(soc_desc, self.io.soc, self.aoi_io, self.output)
        downloads = drive_handler.download_to_disk(productivity_desc, self.io.productivity, self.aoi_io, self.output)
        downloads = drive_handler.download_to_disk(indicator_15_3_1_desc, self.io.indicator_15_3_1, self.aoi_io, self.output)
        
        # I assume that they are always launch at the same time 
        # If not it's going to crash
        if downloads:
            utils.wait_for_completion([land_cover_desc, soc_desc, productivity_desc, indicator_15_3_1_desc], self.output)
        self.output.add_live_msg('GEE tasks completed', 'success') 
        
        # digest the tiles
        digest_tiles(self.aoi_io, land_cover_desc, pm.result_dir, self.output, pm.result_dir.joinpath(f'{land_cover_desc}_merge.tif'))
        digest_tiles(self.aoi_io, soc_desc, pm.result_dir, self.output, pm.result_dir.joinpath(f'{soc_desc}_merge.tif'))
        digest_tiles(self.aoi_io, productivity_desc, pm.result_dir, self.output, pm.result_dir.joinpath(f'{productivity_desc}_merge.tif'))
        digest_tiles(self.aoi_io, indicator_15_3_1_desc, pm.result_dir, self.output, pm.result_dir.joinpath(f'{indicator_15_3_1_desc}_merge.tif'))
        
        # remove the files from drive
        drive_handler.delete_files(drive_handler.get_files(land_cover_desc))
        drive_handler.delete_files(drive_handler.get_files(soc_desc))
        drive_handler.delete_files(drive_handler.get_files(productivity_desc))
        drive_handler.delete_files(drive_handler.get_files(indicator_15_3_1_desc))
        
        #display msg 
        self.output.add_live_msg('Download complete', 'success')
        
        widget.toggle_loading()
            
        return
        
def digest_tiles(aoi_io, filename, result_dir, output, tmp_file):
    
    drive_handler = gdrive.gdrive()
    files = drive_handler.get_files(filename)
    
    # if no file, it means that the download had failed
    if not len(files):
        raise Exception(ms.NO_FILES)
        
    drive_handler.download_files(files, result_dir)
    
    pathname = f'{filename}*.tif'
    
    files = [file for file in result_dir.glob(pathname)]
        
    #run the merge process
    output.add_live_msg("merge tiles")
    time.sleep(2)
    
    #manual open and close because I don't know how many file there are
    sources = [rio.open(file) for file in files]

    data, output_transform = merge(sources)
    
    out_meta = sources[0].meta.copy()    
    out_meta.update(
        driver    = "GTiff",
        height    =  data.shape[1],
        width     =  data.shape[2],
        transform = output_transform,
        compress  = 'lzw'
    )
    
    with rio.open(tmp_file, "w", **out_meta) as dest:
        dest.write(data)
    
    # manually close the files
    [src.close() for src in sources]
    
    # delete local files
    [file.unlink() for file in files]
    
    return
        
        
        