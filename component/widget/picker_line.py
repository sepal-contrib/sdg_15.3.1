import ipyvuetify as v

from component import parameter as pm
from component.message import ms


class PickerLine(v.Layout):

    YEAR_RANGE = [y for y in range(pm.sensor_max_year, pm.L4_start - 1, -1)]

    def __init__(self, model):

        self.model = model

        # create the widgets
        self.start_picker = v.Select(
            label=ms.start_lbl,
            items=self.YEAR_RANGE,
            xs4=True,
            v_model=None,
            class_="ml-5 mr-5",
        )
        self.end_picker = v.Select(
            label=ms.end_lbl,
            items=self.YEAR_RANGE,
            xs4=True,
            v_model=None,
            class_="ml-5 mr-5",
        )

        # bind them to the output
        model.bind(self.start_picker, "start").bind(self.end_picker, "end")

        super().__init__(xs=12, row=True, children=[self.start_picker, self.end_picker])
