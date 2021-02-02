import ipyvuetify as v
from sepal_ui import sepalwidgets as sw
from sepal_ui import mapping as sm

from component import widget as cw 
from component import scripts as cs
from component import parameter as pm

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
        pickers = cw.PickerLine(self.io, self.output)
        self.sensor_select = cw.SensorSelect(items=[], label="select sensor", multiple=True, v_model=None, chips=True)
        trajectory = v.Select(label='trajectory', items=pm.trajectories, v_model=None)
        transition_label = v.Html(class_='grey--text mt-2', tag='h3', children=['Transition matrix'])
        transition_matrix = cw.TransitionMatrix(self.io, self.output)
        climate_regime = cw.ClimateRegime(self.io, self.output)
        
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
        if not self.output.check_input(self.aoi_io.get_aoi_name(), 'no aoi'): return widget.toggle_loading()
        if not self.output.check_input(self.io.start, 'no start'): return widget.toggle_loading()
        if not self.output.check_input(self.io.target_start, 'no target'): return widget.toggle_loading()
        if not self.output.check_input(self.io.end, 'no end'): return widget.toggle_loading()
        if not self.output.check_input(self.io.trajectory, 'no trajectory'): return widget.toggle_loading()
        # will work in next sepal_ui patch
        #if not self.output.check_input(self.io.sensors, 'no sensors'): return widget.toggle_loading()
        
        try: 
            cs.compute_indicator_maps(self.aoi_io, self.io, self.output)

            # create the csv result
            #stats = cs.compute_zonal_analysis(self.aoi_io, self.io, self.output)
            #self.result_tile.shp_btn.set_url(str(stats))

            # get the result map        
            cs.display_maps(self.aoi_io, self.io, self.result_tile.m, self.output)
        
            # release the download btn
            self.result_tile.tif_btn.disabled = False
        
        except Exception as e:
            self.output.add_live_msg(str(e), 'error')
        
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
        # with its legend
        self.m = sm.SepalMap() 
        self.m.add_legend(
            legend_title = 'Indicators state', 
            legend_dict=pm.legend_test, 
            position='topleft'
        )
        
        # add a download btn for csv and a download btn for the sepal
        self.shp_btn = sw.DownloadBtn('zonal statistics')
        self.prod_btn = sw.DownloadBtn('productivity')
        self.land_cover_btn = sw.DownloadBtn('land cover')
        self.soc_btn = sw.DownloadBtn('soil organic carbon')
        self.indicator_btn = sw.DownloadBtn('indicator 15.3.1')
        
        self.tif_btn = sw.Btn(text = 'Download maps as .tif in sepal',icon = 'mdi-download', class_='ma-5')
        self.tif_btn.disabled = True
        
        # aggregate the btn as a line 
        btn_line =  v.Layout(Row=True, children=[
            self.shp_btn, 
            self.prod_btn,
            self.land_cover_btn,
            self.soc_btn,
            self.indicator_btn
        ])
        
        # init the tile 
        super().__init__(
            '15_3_1_widgets', 
            'Results', 
            [btn_line, self.m],
            output = self.output, 
            btn = self.tif_btn
        )
        
        # link the downlad as tif to a function
        self.tif_btn.on_event('click', self.download_maps)
        
        
    def download_maps(self, widget, event, data):
        
        widget.toggle_loading()
        
        try:
            # download the files 
            links = cs.download_maps(self.aoi_io, self.io, self.output)
            
            # update the btns
            self.land_cover_btn.set_url(str(links[0]))
            self.soc_btn.set_url(str(links[1]))
            self.prod_btn.set_url(str(links[2]))
            self.indicator_btn.set_url(str(links[3]))
        
        except Exception as e:
            self.output.add_live_msg(str(e), 'error')
            
        widget.toggle_loading()
            
        return
        