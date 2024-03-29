from sepal_ui import sepalwidgets as sw
from sepal_ui.scripts import utils as su

from component.message import cm
from component import scripts as cs


class ZonalTile(sw.Tile):
    def __init__(self, aoi_model, model, **kwargs):
        # get model for the downloading
        self.aoi_model = aoi_model
        self.model = model

        markdown = sw.Markdown("""{}""".format("  \n".join(cm.result_text_zonalstats)))

        # init the tile
        super().__init__(
            "result_tile",
            cm.titles.zonal,
            [markdown],
            alert=sw.Alert(),
            btn=sw.Btn(
                text=cm.result_btn_zonalstats,
                icon="mdi-download",
                class_="ma-5",
                disabled=True,
            ),
        )

        # link the downlad as tif to a function
        self.btn.on_event("click", self.compute_stats)

    @su.loading_button()
    def compute_stats(self, widget, event, data):
        # download the files
        stats = cs.compute_zonal_analysis(self.aoi_model, self.model, self.alert)

        return
