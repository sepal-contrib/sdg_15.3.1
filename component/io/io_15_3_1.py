from component import parameter as pm

class Io_15_3_1():
    
    def __init__(self):
        
        #####################
        ##      input      ##
        #####################
        # times
        self.start = None
        self.target_start = None
        self.baseline_end_picker = None
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
        