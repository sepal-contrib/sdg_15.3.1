import ipyvuetify as v
from sepal_ui import sepalwidgets as sw
from sepal_ui.scripts import utils as su
import matplotlib.pyplot as plt

from component.message import ms
from component import widget as cw
from component import parameter as cp
from component import scripts as cs


class InputTile(sw.Tile):
    def __init__(self, aoi_model, model, result_tile, zonal_stats_tile):

        # use model
        self.aoi_model = aoi_model
        self.model = model

        # output before everything to link in the matrix widget
        alert = sw.Alert()

        # result tile
        self.result_tile = result_tile

        # Zonal stats tile
        self.zonal_stats_tile = zonal_stats_tile

        # create the widgets that will be displayed
        markdown = sw.Markdown("""{}""".format("  \n".join(ms._15_3_1.process_text)))
        pickers = cw.PickerLine(self.model)
        self.sensor_select = cw.SensorSelect()
        vegetation_index = v.Select(
            label=ms._15_3_1.vi_lbl,
            items=cp.vegetation_index,
            v_model=cp.vegetation_index[0]["value"],
        )
        trajectory = v.Select(
            label=ms._15_3_1.traj_lbl,
            items=cp.trajectories,
            v_model=cp.trajectories[0]["value"],
        )
        lceu = v.Select(
            label=ms._15_3_1.lceu_lbl, items=cp.lceu, v_model=cp.lceu[0]["value"]
        )

        climate_regime = cw.ClimateRegime(self.model, alert)

        # create advanced parameters
        transition_label = v.Html(
            class_="grey--text mt-2", tag="h3", children=[ms._15_3_1.transition_matrix]
        )
        transition_matrix = cw.TransitionMatrix(self.model, alert)
        start_lc = cw.SelectLC(label=ms._15_3_1.start_lc)
        end_lc = cw.SelectLC(label=ms._15_3_1.end_lc)

        # stack the advance parameters in a expandpanel
        advance_params = v.ExpansionPanels(
            class_="mb-5",
            popout=True,
            children=[
                v.ExpansionPanel(
                    children=[
                        v.ExpansionPanelHeader(children=[ms._15_3_1.advance_params]),
                        v.ExpansionPanelContent(
                            children=[
                                v.Flex(xs12=True, children=[start_lc]),
                                v.Flex(xs12=True, children=[end_lc]),
                                v.Flex(xs12=True, children=[transition_label]),
                                v.Flex(xs12=True, children=[transition_matrix]),
                            ]
                        ),
                    ]
                )
            ],
        )

        # bind the standars widgets to variables
        (
            self.model.bind(self.sensor_select, "sensors")
            .bind(trajectory, "trajectory")
            .bind(vegetation_index, "vegetation_index")
            .bind(lceu, "lceu")
            .bind(start_lc.w_image, "start_lc")
            .bind(start_lc.w_band, "start_lc_band")
            .bind(end_lc.w_image, "end_lc")
            .bind(end_lc.w_band, "end_lc_band")
        )

        # create the actual tile
        super().__init__(
            "input_tile",
            ms._15_3_1.titles.inputs,
            inputs=[
                markdown,
                pickers,
                self.sensor_select,
                vegetation_index,
                trajectory,
                lceu,
                climate_regime,
                advance_params,
            ],
            btn=sw.Btn(ms._15_3_1.process_btn, class_="mt-5"),
            alert=alert,
        )

        # add links between the widgets
        self.btn.on_event("click", self.start_process)
        pickers.end_picker.observe(self.sensor_select.update_sensors, "v_model")

    @su.loading_button(debug=True)
    def start_process(self, widget, data, event):

        # check the inputs
        if not all(
            [
                self.alert.check_input(self.aoi_model.name, ms.error.no_aoi),
                self.alert.check_input(self.model.start, ms._15_3_1.error.no_start),
                self.alert.check_input(self.model.end, ms._15_3_1.error.no_end),
                self.alert.check_input(
                    self.model.vegetation_index, ms._15_3_1.error.no_vi
                ),
                self.alert.check_input(self.model.trajectory, ms._15_3_1.error.no_traj),
                self.alert.check_input(self.model.lceu, ms._15_3_1.error.no_lceu),
                self.alert.check_input(self.model.sensors, "no sensors"),
            ]
        ):
            return
        if self.model.start_lc or self.model.end_lc:
            if not self.alert.check_input(
                self.model.start_lc == self.model.end_lc,
                "the lc custom class need to be all set. If two Images have been set, they need to be different.",
            ):
                return

        # create a result folder including the data parameters
        # create the aoi and parameter folder if not existing
        aoi_dir = cp.result_dir / su.normalize_str(self.aoi_model.name)
        result_dir = aoi_dir / self.model.folder_name()
        result_dir.mkdir(parents=True, exist_ok=True)

        # compute the indicators maps
        cs.compute_indicator_maps(self.aoi_model, self.model, self.alert)

        # get the result map
        cs.display_maps(self.aoi_model, self.model, self.result_tile.m, self.alert)

        # get the land transition data
        df = cs.compute_lc_transition_stats(self.aoi_model, self.model)

        # get the stats by lc
        dflc = cs.compute_stats_by_lc(self.aoi_model, self.model)
        pivot_dflc = dflc.pivot(index="Landcover", columns="Indicator")["Area"]

        # create the diagrams
        self.result_tile.sankey_plot.clear_output()
        self.result_tile.bar_plot.clear_output()

        with plt.style.context("dark_background"):
            with self.result_tile.sankey_plot:
                fig, ax = cs.sankey(df=df, colorDict=cp.lc_color, aspect=4, fontsize=12)
                fig.set_facecolor((0, 0, 0, 0))
                plt.show()

            with self.result_tile.bar_plot:
                fig, ax = cs.bar_plot(pivot_dflc)
                ax.set_facecolor((0, 0, 0, 0))
                fig.set_facecolor((0, 0, 0, 0))
                plt.show()

        # save the figures by default
        pattern = str(result_dir / f"{self.aoi_model.name}_{self.model.folder_name()}")
        fig, ax = cs.sankey(df=df, colorDict=cp.lc_color, aspect=4, fontsize=12)
        fig.savefig(f"{pattern}_lc_transition.png", dpi=200)
        plt.close()
        fig, ax = cs.bar_plot(pivot_dflc)
        fig.savefig(f"{pattern}_area_distribution.png")
        plt.close()

        # export the legend by default
        cs.export_legend(
            f"{pattern}_indicator_legend.png", cp.legend, "Indicator Status"
        )
        cs.export_legend(f"{pattern}_lc_legend.png", cp.lc_color, "Land Cover class")

        # release the download btn
        self.result_tile.btn.disabled = False
        self.zonal_stats_tile.btn.disabled = False

        return
