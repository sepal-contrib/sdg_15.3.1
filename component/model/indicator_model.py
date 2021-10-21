from sepal_ui import model
from traitlets import Any

from component import parameter as pm


class IndicatorModel(model.Model):

    #####################
    ##      input      ##
    #####################
    # times
    start = Any(None).tag(sync=True)
    end = Any(None).tag(sync=True)

    # sensors
    sensors = Any(None).tag(sync=True)

    # Vegetation indices
    vegetation_index = Any(None).tag(sync=True)

    # trajectory
    trajectory = Any(None).tag(sync=True)
    lceu = Any(None).tag(sync=True)

    # matrix, change output format to a plain list. we need it to remap the land cover instead of a matrix.
    transition_matrix = Any(pm.default_trans_matrix).tag(sync=True)

    # Climate regime
    conversion_coef = Any(None).tag(sync=True)

    ######################
    ##      output      ##
    ######################

    land_cover = Any(None).tag(sync=True)
    soc = Any(None).tag(sync=True)
    productivity = Any(None).tag(sync=True)
    productivity_trend = Any(None).tag(sync=True)
    productivity_state = Any(None).tag(sync=True)
    productivity_performance = Any(None).tag(sync=True)
    indicator_15_3_1 = Any(None).tag(sync=True)

    def folder_name(self):
        """Return all the parameter formated as a string"""

        # get the dates
        start = self.start
        end = self.end

        # create the sensor list
        if "l" in self.sensors[0]:
            # get only the number of the landsat satelites
            names = [pm.sensors[s][2][1] for s in self.sensors]
            sensor = f"l{''.join(names)}"
        else:
            sensor = pm.sensors[self.sensors[0]][2]

        # get the vegetation index
        vegetation_index = self.vegetation_index

        # get the trajectory
        trajectory = self.trajectory.replace("_trend", "")

        # get land cover ecosystem unit
        lceu = self.lceu

        # get info on the transition matrix
        matrix = (
            "default" if self.transition_matrix == pm.default_trans_matrix else "custom"
        )

        # get the climate regime
        climate = f"cr{int(self.conversion_coef*100)}"

        return f"{start}_{end}_{sensor}_{vegetation_index}_{lceu}_{matrix}_{climate}"
