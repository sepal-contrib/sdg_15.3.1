import ipyvuetify as v

from component import parameter as pm
from component.message import ms
from component import widget as cw


class WaterMask(v.Col):

    MASKS = [
        ms.mask.jrc,
        ms.mask.pixel,
        ms.mask.asset,
    ]

    def __init__(self, model, output):

        self.model = model
        self.output = output

        # create the widgets
        self.type_select = v.Select(
            label=ms.water_mask_option_lbl,
            items=self.MASKS,
            v_model=self.MASKS[0],
        )
        self.pixel_value = v.Slider(
            label=ms.mask.water_pixel_lbl,
            color="blue",
            track_color="blue",
            min=9,
            max=99,
            step=1,
            thumb_label="always",
            v_model=None,
        )
        self.ee_asset = cw.SelectLC(ms.mask.asset_lbl)
        self.seasonality = v.Slider(
            label=ms.mask.season_lbl,
            color="blue",
            min=1,
            max=12,
            step=1,
            thumb_label=True,
            ticks=True,
            tick_labels=pm.jrc_seasonality_tick,
            v_model=8,
        )

        # bind the to the output
        self.model.bind(self.pixel_value, "water_mask_pixel").bind(
            self.ee_asset.w_image, "water_mask_asset_id"
        ).bind(self.ee_asset.w_band, "water_mask_asset_band").bind(
            self.seasonality, "seasonality"
        )

        # hide the components
        self._reset()

        # create the layout
        super().__init__(
            xs12=True,
            class_="mt-5, pa-0",
            children=[
                self.type_select,
                self.seasonality,
                self.pixel_value,
                self.ee_asset,
            ],
        )

        # add some bindinghaza
        self.type_select.observe(self._update_selection, "v_model")

    def _update_selection(self, change):

        # reset the variables
        self._reset()

        if change["new"] == self.MASKS[1]:  # pixel
            self.pixel_value.show()
            self.seasonality.hide()
        elif change["new"] == self.MASKS[2]:  # asset
            self.ee_asset.show()
            self.seasonality.hide()
        elif change["new"] == self.MASKS[0]:  # JRC
            self.seasonality.show()

        return

    def _reset(self):

        # remove values
        self.pixel_value.v_model = None
        self.ee_asset.w_image.v_model = None
        self.ee_asset.w_band.v_model = None

        # hide components
        self.pixel_value.hide()
        self.ee_asset.hide()

        return
