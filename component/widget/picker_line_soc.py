import ipyvuetify as v

from component import parameter as pm
from component.message import cm


class PickerLineSOC(v.Layout):
    YEAR_RANGE = [y for y in range(pm.sensor_max_year, pm.L4_start - 1, -1)]

    def __init__(self, model):
        self.model = model

        # create the widgets

        self.soc_t_start_picker = v.Select(
            label=cm.soc_t_start_lbl,
            items=self.YEAR_RANGE,
            xs4=True,
            v_model=None,
            class_="ml-5 mr-5",
        )
        self.soc_t_end_picker = v.Select(
            label=cm.soc_t_end_lbl,
            items=self.YEAR_RANGE,
            xs4=True,
            v_model=None,
            class_="ml-5 mr-5",
        )
        # bind them to the output
        model.bind(self.soc_t_start_picker, "soc_t_start").bind(
            self.soc_t_end_picker, "soc_t_end"
        )

        super().__init__(
            xs=12, row=True, children=[self.soc_t_start_picker, self.soc_t_end_picker]
        )
