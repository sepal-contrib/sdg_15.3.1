import ipyvuetify as v
from sepal_ui import sepalwidgets as sw
from sepal_ui import mapping as sm
from sepal_ui.scripts import utils as su

from component import widget as cw 
from component import scripts as cs
from component import parameter as pm
from component.message import ms

class Tile_15_3_1(sw.Tile):
    
    def __init__(self, aoi_model, model, result_tile):
        
        # use model 
        self.aoi_model = aoi_model
        self.model = model
        
        # output before everything to link in the matrix widget
        alert = sw.Alert()
        
        #result tile
        self.result_tile = result_tile
        
        # create the widgets that will be displayed
        markdown = sw.Markdown("""{}""".format('  \n'.join(ms._15_3_1.process_text)))
        pickers = cw.PickerLine(self.model)
        self.sensor_select = cw.SensorSelect()
        vegetation_index = v.Select(label=ms._15_3_1.vi_lbl, items = pm.vegetation_index, v_model =None)
        trajectory = v.Select(label=ms._15_3_1.traj_lbl, items=pm.trajectories, v_model=None)
        transition_label = v.Html(class_='grey--text mt-2', tag='h3', children=[ms._15_3_1.transition_matrix])
        transition_matrix = cw.TransitionMatrix(self.model, alert)
        climate_regime = cw.ClimateRegime(self.model, alert)
        
        # bind the standars widgets to variables 
        self.model.bind(self.sensor_select, 'sensors').bind(trajectory, 'trajectory').bind(vegetation_index,'vegetation_index')
        
        # create the actual tile
        super().__init__(
            self.result_tile._metadata['mount_id'],
            ms._15_3_1.title,
            inputs = [
                markdown, 
                pickers, 
                self.sensor_select, 
                vegetation_index,
                trajectory, 
                transition_label, 
                transition_matrix, 
                climate_regime
            ],
            btn = sw.Btn(ms._15_3_1.process_btn, class_='mt-5'),
            alert = alert
        )
        
        # add links between the widgets
        self.btn.on_event('click', self.start_process)
        pickers.end_picker.observe(self.sensor_select.update_sensors, 'v_model')
        self.sensor_select.observe(self._check_sensor, 'v_model')
        
    @su.loading_button(debug=False)
    def start_process(self, widget, data, event):
        
        # check the inputs 
        if not self.alert.check_input(self.aoi_model.name, ms.error.no_aoi): return
        if not self.alert.check_input(self.model.start, ms._15_3_1.error.no_start): return
        if not self.alert.check_input(self.model.target_start, ms._15_3_1.error.no_target): return
        if not self.alert.check_input(self.model.end, ms._15_3_1.error.no_end): return
        if not self.alert.check_input(self.model.vegetation_index, ms._15_3_1.error.no_vi): return
        if not self.alert.check_input(self.model.trajectory, ms._15_3_1.error.no_traj): return
        if not self.alert.check_input(self.model.sensors, 'no sensors'): return widget.toggle_loading()
        
        cs.compute_indicator_maps(self.aoi_model, self.model, self.alert)

        # get the result map        
        cs.display_maps(self.aoi_model, self.model, self.result_tile.m, self.alert)

        # create the csv result
        stats = cs.compute_zonal_analysis(self.aoi_model, self.model, self.alert)
        self.result_tile.shp_btn.set_url(str(stats))

        # release the download btn
        self.result_tile.btn.disabled = False
            
        return
    
    def _check_sensor(self, change):
        """
        prevent users from selecting landsat and sentinel 2 sensors
        provide a warning message to help understanding
        """

        # exit if its a removal 
        if len(change['new']) < len(change['old']):
            self.alert.reset()
            return self

        # use positionning in the list as boolean value
        sensors = ['Landsat', 'Sentinel']

        # guess the new input 
        new_value = list(set(change['new']) - set(change['old']))[0]

        id_ = next(i for i, s in enumerate(sensors) if s in new_value)

        if sensors[id_] in new_value:
            if any(sensors[not id_] in s for s in change['old']):
                change['owner'].v_model = [new_value]
                self.alert.add_live_msg(ms._15_3_1.error.no_mix, 'warning')
            else: 
                self.alert.reset()

        return self
    
class Result_15_3_1(sw.Tile):
    
    def __init__(self, aoi_model, model, **kwargs):
        
        # get model for the downloading 
        self.aoi_model = aoi_model
        self.model = model
        
        markdown = sw.Markdown("""{}""".format('  \n'.join(ms._15_3_1.result_text)))
        
        # create the result map
        # with its legend
        self.m = sm.SepalMap() 
        self.m.add_legend(
            legend_title = ms._15_3_1.map_legend, 
            legend_dict=pm.legend, 
            position='topleft'
        )
        
        # add a download btn for csv and a download btn for the sepal
        self.shp_btn = sw.DownloadBtn(ms._15_3_1.down_zonal)
        self.prod_btn = sw.DownloadBtn(ms._15_3_1.down_prod)
        self.land_cover_btn = sw.DownloadBtn(ms._15_3_1.down_lc)
        self.soc_btn = sw.DownloadBtn(ms._15_3_1.down_soc)
        self.indicator_btn = sw.DownloadBtn(ms._15_3_1.down_ind)
        
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
            ms._15_3_1.results, 
            [markdown, btn_line, self.m],
            alert = sw.Alert(), 
            btn = sw.Btn(text = ms._15_3_1.result_btn, icon = 'mdi-download', class_='ma-5', disabled=True)
        )
        
        # link the downlad as tif to a function
        self.btn.on_event('click', self.download_maps)
        
    @su.loading_button(debug=False)
    def download_maps(self, widget, event, data):
        
        # download the files 
        links = cs.download_maps(self.aoi_model, self.model, self.alert)

        # update the btns
        self.land_cover_btn.set_url(str(links[0]))
        self.soc_btn.set_url(str(links[1]))
        self.prod_btn.set_url(str(links[2]))
        self.indicator_btn.set_url(str(links[3]))
            
        return
        