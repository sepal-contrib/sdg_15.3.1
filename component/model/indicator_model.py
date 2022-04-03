from sepal_ui import model
from traitlets import Any

from component import parameter as pm


class IndicatorModel(model.Model):

    #####################
    ##      input      ##
    #####################
    # Assesment period
    ## Simple
    start = Any(None).tag(sync=True)
    end = Any(None).tag(sync=True)
    ## productivity trend
    trend_start = Any(None).tag(sync=True)
    trend_end = Any(None).tag(sync=True)
    ## productivity state
    state_start = Any(None).tag(sync=True)
    state_end = Any(None).tag(sync=True)
    ## productivity performance
    performance_start = Any(None).tag(sync=True)
    performance_end = Any(None).tag(sync=True)
    ## Land cover
    landcover_t_start = Any(None).tag(sync=True)
    landcover_t_end = Any(None).tag(sync=True)
    ## Soil organic carbon
    soc_t_start = Any(None).tag(sync=True)
    soc_t_end = Any(None).tag(sync=True)

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

    # Custom assessment period

    # check for the custom trend period
    @property
    def p_trend_start(self):
        if self.trend_start:
            return self.trend_start
        else:
            return self.start

    @property
    def p_trend_end(self):
        if self.trend_end:
            return self.trend_end
        else:
            return self.end

    # check for the custom state period
    @property
    def p_state_start(self):
        if self.state_start:
            return self.state_start
        else:
            return self.start

    @property
    def p_state_end(self):
        if self.state_end:
            return self.state_end
        else:
            return self.end

    # check for the custom performance period
    @property
    def p_performance_start(self):
        if self.performance_start:
            return self.performance_start
        else:
            return self.start

    @property
    def p_performance_end(self):
        if self.performance_end:
            return self.performance_end
        else:
            return self.end

    # check for the custom lc period
    @property
    def p_landcover_t_start(self):
        if self.landcover_t_start:
            return self.landcover_t_start
        else:
            return self.start

    @property
    def p_landcover_t_end(self):
        if self.landcover_t_end:
            return self.landcover_t_end
        else:
            return self.end

    # check for the custom soc period
    @property
    def p_soc_t_start(self):
        if self.soc_t_start:
            return self.soc_t_start
        else:
            return self.start

    @property
    def p_soc_t_end(self):
        if self.soc_t_end:
            return self.soc_t_end
        else:
            return self.end

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
