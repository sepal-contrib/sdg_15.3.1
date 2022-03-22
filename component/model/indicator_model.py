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
    vegetation_index = Any(pm.vegetation_index[0]["value"]).tag(sync=True)

    # Productivity lookup table
    productivity_lookup_table = Any(pm.productivity_lookup_table[0]["value"]).tag(
        sync=True
    )

    # trajectory
    trajectory = Any(pm.trajectories[0]["value"]).tag(sync=True)
    lceu = Any(pm.lceu[0]["value"]).tag(sync=True)

    # matrix, change output format to a plain list. we need it to remap the land cover instead of a matrix.
    transition_matrix = Any(pm.default_trans_matrix).tag(sync=True)

    # Climate regime
    conversion_coef = Any(None).tag(sync=True)

    # custom lc
    start_lc = Any(None).tag(sync=True)
    start_lc_band = Any(None).tag(sync=True)
    end_lc = Any(None).tag(sync=True)
    end_lc_band = Any(None).tag(sync=True)

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
        custom_matrix = self.transition_matrix != pm.default_trans_matrix
        custom_lc = self.start_lc is not None
        lc_matrix = "custom" if custom_matrix or custom_lc else "default"

        # get the climate regime
        climate = f"cr{int(self.conversion_coef*100)}"

        return f"{start}_{end}_{sensor}_{vegetation_index}_{lceu}_{lc_matrix}_{climate}"
