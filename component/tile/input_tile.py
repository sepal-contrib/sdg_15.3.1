import ipyvuetify as v
from sepal_ui import sepalwidgets as sw
from sepal_ui.scripts import utils as su
import matplotlib.pyplot as plt

from component.message import ms
from component import widget as cw
from component import parameter as cp
from component import scripts as cs

plt.style.use("dark_background")


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
            label=ms._15_3_1.vi_lbl, items=cp.vegetation_index, v_model=None
        )
        trajectory = v.Select(
            label=ms._15_3_1.traj_lbl, items=cp.trajectories, v_model=None
        )
        lceu = v.Select(label=ms._15_3_1.lceu_lbl, items=cp.lceu, v_model=None)
        transition_label = v.Html(
            class_="grey--text mt-2", tag="h3", children=[ms._15_3_1.transition_matrix]
        )
        transition_matrix = cw.TransitionMatrix(self.model, alert)
        climate_regime = cw.ClimateRegime(self.model, alert)

        # bind the standars widgets to variables
        self.model.bind(self.sensor_select, "sensors").bind(
            trajectory, "trajectory"
        ).bind(vegetation_index, "vegetation_index").bind(lceu, "lceu")

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
                transition_label,
                transition_matrix,
                climate_regime,
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
        if not self.alert.check_input(self.aoi_model.name, ms.error.no_aoi):
            return
        if not self.alert.check_input(self.model.start, ms._15_3_1.error.no_start):
            return
        if not self.alert.check_input(self.model.end, ms._15_3_1.error.no_end):
            return
        if not self.alert.check_input(
            self.model.vegetation_index, ms._15_3_1.error.no_vi
        ):
            return
        if not self.alert.check_input(self.model.trajectory, ms._15_3_1.error.no_traj):
            return
        if not self.alert.check_input(self.model.lceu, ms._15_3_1.error.no_lceu):
            return
        if not self.alert.check_input(self.model.sensors, "no sensors"):
            return widget.toggle_loading()

        cs.compute_indicator_maps(self.aoi_model, self.model, self.alert)

        # get the result map
        cs.display_maps(self.aoi_model, self.model, self.result_tile.m, self.alert)

        # get the land transition data
        df = cs.compute_lc_transition_stats(self.aoi_model, self.model)

        # get the sankey plot
        self.result_tile.sankey_plot.clear_output()
        with self.result_tile.sankey_plot:
            fig, ax = cs.sankey(df=df, colorDict=cp.lc_color, aspect=4, fontsize=12)
            fig.set_facecolor((0, 0, 0, 0))
            plt.show()

        dflc = cs.compute_stats_by_lc(self.aoi_model, self.model)
        pivot_dflc = dflc.pivot(index="Landcover", columns="Indicator")["Area"]
        self.result_tile.bar_plot.clear_output()
        # Get the bar diagram
        with self.result_tile.bar_plot:
            fig, ax = plt.subplots(figsize=(10, 9))
            pivot_dflc.plot.bar(
                rot=0,
                color={
                    "Stable": "#D5B9B2",
                    "Degraded": "#F28482",
                    "Improved": "#4F772D",
                },
                ax=ax,
                fontsize=12,
            )
            ax.set_xlabel("Land cover")
            ax.set_yscale("log")
            ax.set_ylabel("Area in ha")
            ax.set_title("Distribution of area by land cover type")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_visible(False)
            ax.set_facecolor((0, 0, 0, 0))
            fig.set_facecolor((0, 0, 0, 0))
            plt.show()

        # release the download btn
        self.result_tile.btn.disabled = False
        self.zonal_stats_tile.btn.disabled = False

        return
