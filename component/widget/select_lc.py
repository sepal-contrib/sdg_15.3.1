from sepal_ui import sepalwidgets as sw
from sepal_ui.scripts import utils as su
import ee
from natsort import natsorted
import ipyvuetify as v

from component.message import ms
from component import parameter as cp

ee.Initialize()


class SelectLC(v.Layout):
    def __init__(self, label="select Land Cover"):

        # create the layout
        super().__init__(row=True, xs12=True)

        # set up the content
        self.w_image = sw.AssetSelect(types=["IMAGE"], label=label)
        self.w_band = v.Select(label="band", v_model=None, items=None, class_="pl-5")

        # create the children item
        self.children = [
            v.Flex(xs8=True, children=[self.w_image]),
            v.Flex(xs4=True, children=[self.w_band]),
        ]

        # js behaviour
        self.w_image.observe(self._validate, "v_model")

    @su.switch("loading", "disabled", on_widgets=["w_image"])
    def _validate(self, change):
        """
        Validate the selected access. Throw an error message if is not accesible.
        If the asset can be accessed check that it only include values within the classification"""

        w = self.w_image  # it's also change["owner"]

        w._validate(change)

        # only check the values if I have access to the asset
        if w.valid == False:
            return

        # the asset need to be an image
        if not w.asset_info["type"] == "IMAGE":
            w.asset_info = None
            w.valid = False
            w.error = True
            w.error_messages = ms.select_lc.not_image
            return

        # call the band list update
        self._update_bands()

        return

    @su.switch("loading", "disabled", on_widgets=["w_band"])
    def _update_bands(self):
        """Update the band possibility to the available bands/properties of the input"""

        # update the bands values
        self.w_band.v_model = None
        self.w_band.items = natsorted(
            ee.Image(self.w_image.v_model).bandNames().getInfo()
        )

        return
