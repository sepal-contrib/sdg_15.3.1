import ipyvuetify as v 

from component import parameter as pm

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