from sepal_ui import sepalwidgets as sw
from sepal_ui.scripts import utils as su

from component.message import ms
from component import scripts as cs


class ZonalTile(sw.Tile):
    def __init__(self, aoi_model, model, **kwargs):

        # get model for the downloading
        self.aoi_model = aoi_model
        self.model = model

        markdown = sw.Markdown(
            """{}""".format("  \n".join(ms._15_3_1.result_text_zonalstats))
        )

        # init the tile
        super().__init__(
            "result_tile",
            ms._15_3_1.titles.zonal,
            [markdown],
            alert=sw.Alert(),
            btn=sw.Btn(
                text=ms._15_3_1.result_btn_zonalstats,
                icon="mdi-download",
                class_="ma-5",
                disabled=True,
            ),
        )

        # link the downlad as tif to a function
        self.btn.on_event("click", self.compute_stats)

    @su.loading_button(debug=False)
    def compute_stats(self, widget, event, data):

        # download the files
        stats = cs.compute_zonal_analysis(self.aoi_model, self.model, self.alert)

        return
