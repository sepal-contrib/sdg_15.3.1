import ipyvuetify as v
from sepal_ui import sepalwidgets as sw
from sepal_ui.scripts import utils as su
from sepal_ui import mapping as sm
from ipywidgets import Output, link

from component.message import ms
from component import parameter as cp
from component import scripts as cs


class ResultTile(sw.Tile):
    def __init__(self, aoi_model, model, **kwargs):

        # get model for the downloading
        self.aoi_model = aoi_model
        self.model = model

        markdown = sw.Markdown("""{}""".format("  \n".join(ms._15_3_1.result_text)))

        # create the result map
        # with its legend
        self.m = sm.SepalMap()
        self.m.add_legend(
            legend_title=ms._15_3_1.map_legend,
            legend_dict=cp.legend,
            position="topleft",
        )

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

        # add a download btn for csv and a download btn for the sepal

        self.prod_btn = sw.DownloadBtn(ms._15_3_1.down_prod)
        self.trend_btn = sw.DownloadBtn(ms._15_3_1.down_trend)
        self.state_btn = sw.DownloadBtn(ms._15_3_1.down_state)
        self.performance_btn = sw.DownloadBtn(ms._15_3_1.down_performance)
        self.land_cover_btn = sw.DownloadBtn(ms._15_3_1.down_lc)
        self.soc_btn = sw.DownloadBtn(ms._15_3_1.down_soc)
        self.indicator_btn = sw.DownloadBtn(ms._15_3_1.down_ind)

        # aggregate the btn as a line
        btn_line = v.Layout(
            children=[
                self.trend_btn,
                self.state_btn,
                self.performance_btn,
                self.prod_btn,
                self.land_cover_btn,
                self.soc_btn,
                self.indicator_btn,
            ],
            wrap=True,
        )

        # init the tile
        super().__init__(
            "result_tile",
            ms._15_3_1.titles.results,
            [markdown, plot_line, btn_line],
            alert=sw.Alert(),
            btn=sw.Btn(
                text=ms._15_3_1.result_btn,
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

        # update the btns
        self.land_cover_btn.set_url(str(links[0]))
        self.soc_btn.set_url(str(links[1]))
        self.trend_btn.set_url(str(links[2]))
        self.performance_btn.set_url(str(links[3]))
        self.state_btn.set_url(str(links[4]))
        self.prod_btn.set_url(str(links[5]))
        self.indicator_btn.set_url(str(links[6]))

        return
