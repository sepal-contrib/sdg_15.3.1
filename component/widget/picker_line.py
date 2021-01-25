import ipyvuetify as v

from component import parameter as pm

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
        output \
            .bind(self.start_picker, io, 'start') \
            .bind(self.target_picker, io, 'target_start') \
            .bind(self.end_picker, io, 'end')
        
        super().__init__(xs=12, row=True,  children=[self.start_picker, self.target_picker, self.end_picker])