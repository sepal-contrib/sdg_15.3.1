import ipyvuetify as v

from component import parameter as pm
from component.message import ms


class PickerLineProductivity(v.Layout):

    YEAR_RANGE = [y for y in range(pm.sensor_max_year, pm.L4_start - 1, -1)]

    def __init__(self, model):

        self.model = model

        # create the widgets
        self.trend_start_picker = v.Select(
            label=ms.trend_start_lbl,
            items=self.YEAR_RANGE,
            xs4=True,
            v_model=None,
            class_="ml-5 mr-5",
        )
        self.trend_end_picker = v.Select(
            label=ms.trend_end_lbl,
            items=self.YEAR_RANGE,
            xs4=True,
            v_model=None,
            class_="ml-5 mr-5",
        )
        self.state_start_picker = v.Select(
            label=ms.state_start_lbl,
            items=self.YEAR_RANGE,
            xs4=True,
            v_model=None,
            class_="ml-5 mr-5",
        )
        self.state_end_picker = v.Select(
            label=ms.state_end_lbl,
            items=self.YEAR_RANGE,
            xs4=True,
            v_model=None,
            class_="ml-5 mr-5",
        )
        self.performance_start_picker = v.Select(
            label=ms.performance_start_lbl,
            items=self.YEAR_RANGE,
            xs4=True,
            v_model=None,
            class_="ml-5 mr-5",
        )
        self.performance_end_picker = v.Select(
            label=ms.performance_end_lbl,
            items=self.YEAR_RANGE,
            xs4=True,
            v_model=None,
            class_="ml-5 mr-5",
        )
        # bind them to the output
        model.bind(self.trend_start_picker, "trend_start").bind(
            self.trend_end_picker, "trend_end"
        ).bind(self.state_start_picker, "state_start").bind(
            self.state_end_picker, "state_end"
        ).bind(
            self.performance_start_picker, "performance_start"
        ).bind(
            self.performance_end_picker, "performance_end"
        )

        super().__init__(
            row=True,
            children=[
                v.Flex(xs12=True, md6=True, children=[self.trend_start_picker]),
                v.Flex(xs12=True, md6=True, children=[self.trend_end_picker]),
                v.Flex(xs12=True, md6=True, children=[self.state_start_picker]),
                v.Flex(xs12=True, md6=True, children=[self.state_end_picker]),
                v.Flex(xs12=True, md6=True, children=[self.performance_start_picker]),
                v.Flex(xs12=True, md6=True, children=[self.performance_end_picker]),
            ],
        )
