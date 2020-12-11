from sepal_ui import sepalwidgets as sw
import ipyvuetify as v
from datetime import datetime

from scripts import parameter as pm

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
        
        # matrix 
        self.transition_matrix = [[0 for i in range(7)] for i in range(7)]
        
        
class PickerLine(v.Layout):
    
    YEAR_RANGE = [y for y in range(datetime.now().year, pm.L4_start - 1, -1)]
    
    def __init__(self, io, output):
        
        self.io = io
        self.output = output
        
        start_picker = v.Select(label='Start year', items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        output.bind(start_picker, io, 'start')
        
        target_picker = v.Select(label='Start year of the target period', items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        output.bind(target_picker, io, 'target_start')
        
        end_picker = v.Select(label='End year', items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        output.bind(end_picker, io, 'end')
        
        super().__init__(xs=12, row=True,  children=[start_picker, target_picker, end_picker])
        
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
                
            row = v.Html(tag='tr', children=[v.Html(tag='th', children=[baseline])] + inputs)
            rows.append(row)
            
        # create the simple table 
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
    
    SENSORS = {
        'Landsat 4': 'L4',
        'Landsat 5': 'L5',
        'Landsat 6': 'L6',
        'Landsat 7': 'L7', 
        'Landsat 8': 'L8', 
        'Sentinel 2': 'S2'
    }
    
    TRAJECTORIES = ['NDVI trend', 'RUE', 'RESTREND']
    
    def __init__(self, aoi_io):
        
        # use io 
        self.aoi_io = aoi_io
        self.io = TileIo()
        
        # output
        output = sw.Alert()
        
        markdown = sw.Markdown('Some explainations should go here')
        
        sensor_select = v.Select(items=[*self.SENSORS], label="select sensor", multiple=True, v_model=None)
        output.bind(sensor_select, self.io, 'sensors')
        
        pickers = PickerLine(self.io, output)
        
        trajectory = v.Select(label='trajectory', items=self.TRAJECTORIES, v_model=None)
        output.bind(trajectory, self.io, 'trajectory')
        
        transition_label = v.Html(class_='grey--text mt-2', tag='h3', children=['Transition matrix'])
        
        transition_matrix = TransitionMatrix(self.io, output)
        
        btn = sw.Btn(class_='mt-5')
        
        super().__init__(
            '15_3_1_widgets',
            '15.3.1 Proportion of degraded land over total land area',
            inputs = [markdown, pickers, sensor_select, trajectory, transition_label, transition_matrix],
            btn = btn,
            output = output
        )