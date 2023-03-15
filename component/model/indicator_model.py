from sepal_ui import model
from traitlets import Any
import csv
import re
import random
import matplotlib.colors as pltc
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

    # Vegetation Index thresholds value
    threshold = Any(None).tag(synch=True)

    # Productivity lookup table
    productivity_lookup_table = Any(pm.productivity_lookup_table[0]["value"]).tag(
        sync=True
    )

    # trajectory
    trajectory = Any(pm.trajectories[0]["value"]).tag(sync=True)
    lceu = Any(pm.lceu[0]["value"]).tag(sync=True)

    # matrix, change output format to a plain list. we need it to remap the land cover instead of a matrix.
    transition_matrix = Any(pm.default_trans_matrix).tag(sync=True)
    custom_matrix_file = Any(None).tag(sync=True)

    # Climate regime
    conversion_coef = Any(None).tag(sync=True)

    # custom lc
    start_lc = Any(None).tag(sync=True)
    start_lc_band = Any(None).tag(sync=True)
    end_lc = Any(None).tag(sync=True)
    end_lc_band = Any(None).tag(sync=True)

    ## Water mask
    water_mask_pixel = Any(None).tag(sync=True)
    water_mask_asset_id = Any(None).tag(sync=True)
    water_mask_asset_band = Any(None).tag(sync=True)
    seasonality = Any(None).tag(sync=True)
    lc_pixel_check = Any(None).tag(sync=True)

    # analysis scale
    # from the first sensor (we only combine compatible one)
    @property
    def scale(self):
        return pm.sensors[self.sensors[0]][1]

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

    # Handle case of year_start/end that isn't included in the CCI data
    @property
    def lc_year_start_esa(self):
        return min(
            max(self.p_landcover_t_start, pm.land_cover_first_year),
            pm.land_cover_max_year,
        )

    @property
    def lc_year_end_esa(self):
        return min(
            max(self.p_landcover_t_end, pm.land_cover_first_year),
            pm.land_cover_max_year,
        )

    ##Custom land cover matrix and related parameters
    # read the custom land cover matrix csv file
    @property
    def custom_lc_matrix_list(self):
        return self.csv_reader()

    # save the matrix
    @property
    def custom_transition_matrix(self):
        return [i[2:] for i in self.custom_lc_matrix_list[2:]]

    # save the class list and remove unwanted sysmbols including undescores
    @property
    def lc_classlist_end(self):
        if self.start_lc and self.end_lc and self.custom_matrix_file:
            lc_class = self.custom_lc_matrix_list[0][2:]
            pattern = re.compile(r"[^a-zA-Z -]+")
            lc_class = [re.sub(pattern, "", x.strip()) for x in lc_class]
        else:
            lc_class = pm.lc_class
        return lc_class

    @property
    def lc_classlist_start(self):
        if self.start_lc and self.end_lc and self.custom_matrix_file:
            lc_class = [x[0] for x in self.custom_lc_matrix_list[2:]]
            pattern = re.compile(r"[^a-zA-Z -]+")
            lc_class = [re.sub(pattern, "", x.strip()) for x in lc_class]
        else:
            lc_class = pm.lc_class
        return lc_class

    # save the class code list and make a combination of all possible transitions
    @property
    def lc_codelist_end(self):
        if self.start_lc and self.end_lc and self.custom_matrix_file:
            lc_code_str = self.custom_lc_matrix_list[1][2:]
            lc_code = [int(v) for v in lc_code_str]
        else:
            lc_code = pm.lc_code
        return lc_code

    @property
    def lc_codelist_start(self):
        if self.start_lc and self.end_lc and self.custom_matrix_file:
            lc_code_str = [x[1] for x in self.custom_lc_matrix_list[2:]]
            lc_code = [int(v) for v in lc_code_str]
        else:
            lc_code = pm.lc_code
        return lc_code

    @property
    def lc_class_combination(self):
        return [
            int(str(lc_code_start) + str(lc_code_end))
            for lc_code_start in self.lc_codelist_start
            for lc_code_end in self.lc_codelist_end
        ]

    # flatten the land cover matrix
    @property
    def trans_matrix_flatten(self):
        if self.start_lc and self.end_lc and self.custom_matrix_file:
            matrix_flatten = [
                int(item)
                for sublist in self.custom_transition_matrix
                for item in sublist
            ]
        else:
            matrix_flatten = [
                item for sublist in self.transition_matrix for item in sublist
            ]
        return matrix_flatten

    # create a dictionary of land cover colours
    @property
    def lc_color(self):
        if self.start_lc and self.end_lc and self.custom_matrix_file:
            all_colors = [hx for _, hx in pltc.cnames.items()]
            random.seed(100)
            colors = random.sample(all_colors, len(self.lc_classlist_start))
            sorted_classes = list(
                dict(
                    sorted(
                        {
                            x: y
                            for x, y in zip(
                                self.lc_codelist_start, self.lc_classlist_start
                            )
                        }.items()
                    )
                ).values()
            )
            lc_color = dict(zip(sorted_classes, colors))
        else:
            lc_color = pm.lc_color
        return lc_color

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

    ##Csv reader
    def csv_reader(self):
        with open(self.custom_matrix_file, "r") as csv_file:
            lc_matrix = csv.reader(csv_file)
            lc_matrix_list = []
            for line in lc_matrix:
                lc_matrix_list.append(line)
        return lc_matrix_list
