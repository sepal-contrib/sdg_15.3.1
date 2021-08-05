from sepal_ui import model
from traitlets import Any

from component import parameter as pm

class Model_15_3_1(model.Model):
         
    #####################
    ##      input      ##
    #####################
    # times
    start = Any(None).tag(sync=True)
    end = Any(None).tag(sync=True)

    # sensors
    sensors = Any(None).tag(sync=True)
    
    #Vegetation indices
    
    vegetation_index =Any(None).tag(sync=True)
    # trajectory 
    trajectory = Any(None).tag(sync=True)
    lceu = Any(None).tag(sync=True)

    # matrix, change output format to a plain list. we need it to remap the land cover instead of a matrix.
    transition_matrix = Any(pm.default_trans_matrix).tag(sync=True)

    #Climate regime
    conversion_coef =Any(None).tag(sync=True)

    ######################
    ##      output      ##
    ######################

    land_cover = Any(None).tag(sync=True)
    soc = Any(None).tag(sync=True)
    productivity = Any(None).tag(sync=True)
    indicator_15_3_1 = Any(None).tag(sync=True)
        
