import ipyvuetify as v
from sepal_ui import sepalwidgets as sw
from sepal_ui.scripts import utils as su
from sepal_ui import mapping as sm
from ipywidgets import Output, link
from ipyleaflet import LegendControl

from component.message import ms
from component import parameter as cp
from component import scripts as cs
from component import widget as cw


class ResultTile(sw.Tile):
    def __init__(self, aoi_model, model, **kwargs):

        # get model for the downloading
        self.aoi_model = aoi_model
        self.model = model

        markdown = sw.Markdown("""{}""".format("  \n".join(ms.result_text)))

        # create the result map
        # with its legend
        self.m = cw.ResultMap()

#        self.m.add_legend(
#            legend_title=ms.map.legend.state,
#            legend_dict=cp.legend,
#            position="topleft",
#        )

        # display the graphs next to the map
        self.sankey_plot = Output()
        self.bar_plot = Output()

        self.tabs = v.Tabs(
            class_="mt-5 mb-5",
            grow=True,
            v_model=0,
            children=[
                v.Tab(children=["Transitions"], key=0),
                v.Tab(children=["Distribution"], key=1),
            ],
        )

        self.content = v.TabsItems(
            v_model=0,
            children=[
                v.TabItem(children=[self.sankey_plot], key=0),
                v.TabItem(children=[self.bar_plot], key=1),
            ],
        )

        plot_line = v.Layout(
            row=True,
            xs12=True,
            children=[
                v.Flex(
                    xs12=True,
                    md6=True,
                    class_="pa-5",
                    children=[self.tabs, self.content],
                ),
                v.Flex(xs12=True, md6=True, class_="pa-1", children=[self.m]),
            ],
        )

        # init the tile
        super().__init__(
            "result_tile",
            ms.titles.results,
            [markdown, plot_line],
            alert=sw.Alert(),
            btn=sw.Btn(
                text=ms.result_btn,
                icon="mdi-download",
                class_="ma-5",
                disabled=True,
            ),
        )

        # link the downlad as tif to a function
        self.btn.on_event("click", self.download_maps)
        link((self.tabs, "v_model"), (self.content, "v_model"))

    @su.loading_button(debug=True)
    def download_maps(self, widget, event, data):

        # download the files
        links = cs.download_maps(self.aoi_model, self.model, self.alert)

        return
