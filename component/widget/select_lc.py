from sepal_ui import sepalwidgets as sw
from sepal_ui.scripts import utils as su
import ee

from component.message import ms
from component import parameter as cp

ee.Initialize()


class SelectLC(sw.AssetSelect):
    def __init__(self, **kwargs):

        super().__init__(types=["IMAGE"], **kwargs)

    @su.switch("loading")
    def _validate(self, change):
        """
        Validate the selected access. Throw an error message if is not accesible.
        If the asset can be accessed check that it only include values within the classification"""

        super()._validate(change)

        # only check the values if I have access to the asset
        if self.valid == False:
            return

        # the asset need to be an image
        if not self.asset_info["type"] == "IMAGE":
            self.asset_info = None
            self.valid = False
            self.error = True
            self.error_messages = ms.select_lc.not_image
            return

        # the asset need to be reclassified as a UNCCD LC map
        image = ee.Image(self.v_model).select(0)
        geometry = image.geometry()
        reduction = image.reduceRegion(
            ee.Reducer.frequencyHistogram(), geometry, maxPixels=1e13
        )

        values = ee.Dictionary(reduction.get(image.bandNames().get(0))).keys().getInfo()

        if not all(v in list(range(1, 8)) for v in values):
            self.asset_info = None
            self.valid = False
            self.error = True
            self.error_messages = ms.select_lc.not_unccd
            return

        return
