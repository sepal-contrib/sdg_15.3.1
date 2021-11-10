import ipyvuetify as v
from sepal_ui.scripts import utils as su

from component import parameter as pm
from component.message import ms


class ClimateRegime(v.Col):

    REGIMES = [
        ms.clim_regim.per_pixel,
        ms.clim_regim.predifined,
        ms.clim_regim.custom,
    ]

    def __init__(self, io, output):

        self.io = io
        self.output = output

        # create the widgets
        self.type_select = v.Select(
            label=ms.clim_option_lbl,
            items=self.REGIMES,
            v_model=self.REGIMES[0],
        )
        self.climate_regimes = v.Select(
            label=ms.clim_default_lbl, items=pm.climate_regimes, v_model=None
        )
        self.custom_regime = v.Slider(
            label=ms.clim_custom_lbl, max=1, step=0.01, v_model=None
        )

        # bind the to the output
        output.bind(self.climate_regimes, io, "conversion_coef").bind(
            self.custom_regime, io, "conversion_coef"
        )

        # hide the components
        self._reset()

        # create the layout
        super().__init__(
            xs12=True,
            class_="mt-5, pa-0",
            children=[self.type_select, self.climate_regimes, self.custom_regime],
        )

        # add some binding
        self.type_select.observe(self._update_selection, "v_model")

    def _update_selection(self, change):

        # reset the variables
        self._reset()

        if change["new"] == self.REGIMES[1]:  # specify
            su.show_component(self.climate_regimes)
        elif change["new"] == self.REGIMES[2]:  # custom
            su.show_component(self.custom_regime)

        return

    def _reset(self):

        # remove values
        self.climate_regimes.v_model = None
        self.custom_regime.v_model = None

        # hide components
        su.hide_component(self.climate_regimes)
        su.hide_component(self.custom_regime)

        return
