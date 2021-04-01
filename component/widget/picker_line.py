import ipyvuetify as v

from component import parameter as pm
from component.message import ms

class PickerLine(v.Layout):
    
    YEAR_RANGE = [y for y in range(pm.sensor_max_year, pm.L4_start - 1, -1)]
    
    def __init__(self, io, output):
        
        self.io = io
        self.output = output
        
        # create the widgets
        self.start_picker = v.Select(label=ms._15_3_1.start_lbl, items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        self.baseline_end_picker = v.Select(label=ms._15_3_1.baseline_end_lbl, items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        self.target_picker = v.Select(label=ms._15_3_1.target_start_lbl, items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        self.end_picker = v.Select(label=ms._15_3_1.end_lbl, items=self.YEAR_RANGE, xs4=True, v_model=None, class_='ml-5 mr-5')
        
        # bind them to the output
        output \
            .bind(self.start_picker, io, 'start') \
            .bind(self.baseline_end_picker, io, 'baseline_end')
            .bind(self.target_picker, io, 'target_start') \
            .bind(self.end_picker, io, 'end')
        
        super().__init__(xs=12, row=True,  children=[self.start_picker, self.baseline_end_picker, self.target_picker, self.end_picker])
