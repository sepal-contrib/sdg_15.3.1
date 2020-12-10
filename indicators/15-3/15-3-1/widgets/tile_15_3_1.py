from sepal_ui import sepalwidgets as sw
import ipyvuetify as v


class TileIo():
    
    def __init__(self):
        self.dummy = None
        
class PickerLine(v.Layout):
    
    def __init__(self, io):
        
        start_picker = sw.DatePicker('Start', xs4=True)
        #self.output.bind(self.start_picker, self.io, 'start')
        
        target_picker = sw.DatePicker('Start of the target period', xs4=True)
        #self.output.bind(self.start_picker, self.io, 'start')
        
        end_picker = sw.DatePicker('End', xs4=True)
        #self.output.bind(self.end_picker, self.io, 'end')
        
        super().__init__(xs=12, row=True,  children=[start_picker, target_picker, end_picker])
        
class matrix_input(v.Html):
    
    VALUES = [1, 0, -1]
    
    def __init__(self):
        
        self.val = v.Select(dense = True, color = 'white', items = self.VALUES, class_='ma-1', v_model = 0)
        
        super().__init__(
            style_ = f'background-color: {v.theme.themes.dark.primary}',
            tag = 'td',
            children = [self.val]
        )
        
        # connect the color to the value
        self.val.observe(self.color_change, 'v_model')
        
    def color_change(self, change):
        
        # degradation
        if change['new'] == self.VALUES[2]: 
            self.style_ = f'background-color: {v.theme.themes.dark.error}'
        # stable
        elif change['new'] == self.VALUES[1]:
            self.style_ = f'background-color: {v.theme.themes.dark.primary}'
        # Improvement
        elif change['new'] == self.VALUES[0]:
            self.style_ = f'background-color: {v.theme.themes.dark.success}'
            
        return 
        
class TransitionMatrix(v.SimpleTable):
    
    CLASSES = ['Forest', 'Grassland', 'Cropland', 'Wetland', 'Artificial area', 'Bare land', 'water body']
    
    def __init__(self, io):
        
        self.dummy = None
        
        header = [v.Html(tag = 'tr', children = [v.Html(tag = 'th', children = [''])] + [v.Html(tag = 'th', children = [class_]) for class_ in self.CLASSES])]
        
        rows = []
        for baseline in self.CLASSES:
            row = v.Html(tag = 'tr', children = (
                [v.Html(tag = 'th', children = [baseline])]
                + [v.Html(tag = 'td', class_='ma-0 pa-0', children = [matrix_input()]) for target in self.CLASSES]
            ))
            rows.append(row)
            
            
        super().__init__(
            children = [
                v.Html(tag = 'thead', children = header),
                v.Html(tag = 'tbody', children = rows)
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
        
class Tile_15_3_1(sw.Tile):
    
    SENSORS = ['Landsat 4', 'Landsat 5', 'Landsat 6', 'Landsat 7', 'Landsat 8', 'Sentinel 2']
    
    TRAJECTORIES = ['NDVI trend', 'RUE', 'RESTREND']
    
    def __init__(self, aoi_io):
        
        #use io 
        self.aoi_io = aoi_io
        self.io = TileIo()
        
        markdown = sw.Markdown('Some explainations should go here')
        sensor_select = v.Select(items = self.SENSORS, label = "select sensor", multiple = True)
        pickers = PickerLine(self.io)
        trajectory = v.Select(label ='trajectory', items = self.TRAJECTORIES)
        transition_label = v.Html(class_='grey--text mt-2', tag='h3', children =['Transition matrix'])
        transition_matrix = TransitionMatrix(self.io)
        btn = sw.Btn(class_='mt-5')
        output = sw.Alert()
        
        super().__init__(
            '15_3_1_widgets',
            '15.3.1 Proportion of degraded land over total land area',
            inputs = [markdown, sensor_select, pickers, trajectory, transition_label, transition_matrix],
            btn = btn,
            output = output
        )