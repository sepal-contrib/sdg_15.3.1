import ipyvuetify as v
from sepal_ui import sepalwidgets as sw
from sepal_ui.scripts import utils as su
import matplotlib.pyplot as plt

from component.message import cm
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
        markdown = sw.Markdown("""{}""".format("  \n".join(cm.process_text)))
        pickers = cw.PickerLine(self.model)
        pickers_productivity = cw.PickerLineProductivity(self.model)
        threshold = v.Slider(
            label=cm.threshold.threshold_lbl,
            track_color="green",
            min=-1,
            max=1,
            step=0.01,
            thumb_label="always",
            v_model=0,
        )
        pickers_landcover = cw.PickerLineLC(self.model)
        pickers_soc = cw.PickerLineSOC(self.model)
        self.sensor_select = cw.SensorSelect()
        self.vegetation_index = v.Select(
            label=cm.vi_lbl,
            items=cp.vegetation_index,
            v_model=cp.vegetation_index[0]["value"],
        )
        self.trajectory = v.Select(
            label=cm.traj_lbl,
            items=cp.trajectories,
            v_model=cp.trajectories[0]["value"],
        )
        productivity_lookup_table = v.Select(
            label=cm.prod_lookup_lbl,
            items=cp.productivity_lookup_table,
            v_model=cp.productivity_lookup_table[0]["value"],
        )
        lceu = v.Select(label=cm.lceu_lbl, items=cp.lceu, v_model=cp.lceu[0]["value"])

        climate_regime = cw.ClimateRegime(self.model, alert)

        self.default_lc_matrix_bool = cw.BoolQuestion(cm.select_lc.default_matrix_bool)

        self.custom_lc_matrix_bool = cw.BoolQuestion(cm.select_lc.custom_matrix_bool)

        ##############################################################
        ##             create advanced parameters                   ##
        ##############################################################

        ### Create section headings
        # Main heading
        main_heading_label = v.Html(
            class_="red--text text--lighten-3 mt-2",
            tag="h3",
            children=[cm.advance_params],
        )

        # Productivity section
        prod_sec_label = v.Html(
            class_="green--text text--lighten-3 mt-2",
            tag="h3",
            children=[cm.productivity_sec],
        )
        # Land cover section
        landcover_sec_label = v.Html(
            class_="brown--text text--lighten-3 mt-2",
            tag="h3",
            children=[cm.landcover_sec],
        )
        # Land cover transition heading
        transition_label = v.Html(
            class_="grey--text mt-2", tag="h4", children=[cm.transition_matrix]
        )
        # SOC section heading
        SOC_sec_label = v.Html(
            class_="green--text text--lighten-4 mt-2", tag="h3", children=[cm.soc_sec]
        )

        # Input weigtes

        self._transition_matrix = cw.TransitionMatrix(self.model, alert)
        self._transition_matrix.hide()
        start_lc = cw.SelectLC(label=cm.start_lc)
        end_lc = cw.SelectLC(label=cm.end_lc)
        self.custom_matrix_file = sw.FileInput(
            extentions=[".txt", ".tsb", ".csv"],
            label=cm.custom_matrix_csv,
            v_model="",
            clearable=True,
        ).hide()
        lc_pixel_check = v.Switch(label=cm.select_lc.verify_lc_pixel, v_model=True)
        water_mask = cw.WaterMask(self.model, alert)

        # Create expansion panels for the three sub indicators to stack into the adavanced parameter expand panel widget
        # expand panels for productivity parameters

        productivity_e_panel = v.ExpansionPanels(
            class_="mb-5",
            popout=True,
            children=[
                v.ExpansionPanel(
                    children=[
                        v.ExpansionPanelHeader(children=[prod_sec_label]),
                        v.ExpansionPanelContent(
                            children=[
                                v.Flex(xs12=True, children=[threshold]),
                                v.Flex(xs12=True, children=[pickers_productivity]),
                                v.Flex(xs12=True, children=[productivity_lookup_table]),
                            ]
                        ),
                    ]
                )
            ],
        )
        # expand panels for land cover parameters
        land_cover_e_panel = v.ExpansionPanels(
            class_="mb-5",
            popout=True,
            children=[
                v.ExpansionPanel(
                    children=[
                        v.ExpansionPanelHeader(children=[landcover_sec_label]),
                        v.ExpansionPanelContent(
                            children=[
                                v.Flex(xs12=True, children=[pickers_landcover]),
                                v.Flex(xs12=True, children=[start_lc]),
                                v.Flex(xs12=True, children=[end_lc]),
                                v.Flex(xs12=True, children=[water_mask]),
                                v.Flex(xs12=True, children=[transition_label]),
                                v.Flex(
                                    xs12=True, children=[self.default_lc_matrix_bool]
                                ),
                                v.Flex(xs12=True, children=[self._transition_matrix]),
                                v.Flex(
                                    xs12=True, children=[self.custom_lc_matrix_bool]
                                ),
                                v.Flex(xs12=True, children=[self.custom_matrix_file]),
                                v.Flex(xs12=True, children=[lc_pixel_check]),
                            ]
                        ),
                    ]
                )
            ],
        )
        # expand panels for SOC parameters
        soc_e_panel = v.ExpansionPanels(
            class_="mb-5",
            popout=True,
            children=[
                v.ExpansionPanel(
                    children=[
                        v.ExpansionPanelHeader(children=[SOC_sec_label]),
                        v.ExpansionPanelContent(
                            children=[v.Flex(xs12=True, children=[pickers_soc])]
                        ),
                    ]
                )
            ],
        )

        # stack the advance parameters expand panels in an expandpanel
        advance_params = v.ExpansionPanels(
            class_="mb-5",
            popout=True,
            children=[
                v.ExpansionPanel(
                    children=[
                        v.ExpansionPanelHeader(children=[main_heading_label]),
                        v.ExpansionPanelContent(
                            children=[
                                productivity_e_panel,
                                land_cover_e_panel,
                                soc_e_panel,
                            ]
                        ),
                    ]
                )
            ],
        )

        # bind the standars widgets to variables
        (
            self.model.bind(self.trajectory, "trajectory")
            .bind(self.vegetation_index, "vegetation_index")
            .bind(lceu, "lceu")
            .bind(threshold, "threshold")
            .bind(productivity_lookup_table, "productivity_lookup_table")
            .bind(start_lc.w_image, "start_lc")
            .bind(start_lc.w_band, "start_lc_band")
            .bind(end_lc.w_image, "end_lc")
            .bind(end_lc.w_band, "end_lc_band")
            .bind(self.custom_matrix_file, "custom_matrix_file")
            .bind(lc_pixel_check, "lc_pixel_check")
        )

        # create the actual tile
        super().__init__(
            "input_tile",
            cm.titles.inputs,
            inputs=[
                markdown,
                pickers,
                self.sensor_select,
                self.vegetation_index,
                self.trajectory,
                lceu,
                climate_regime,
                advance_params,
            ],
            btn=sw.Btn(cm.process_btn, class_="mt-5"),
            alert=alert,
        )

        # add links between the widgets
        self.btn.on_event("click", self.start_process)
        pickers.end_picker.observe(self.sensor_select.update_sensors, "v_model")
        self.sensor_select.observe(self._sensor_bind, "update")
        self.default_lc_matrix_bool.observe(self._display_default_matrix, "v_model")
        self.custom_lc_matrix_bool.observe(
            self._display_custom_lc_file_selection, "v_model"
        )

    @su.loading_button()
    def start_process(self, widget, data, event):
        # check the inputs
        if not all(
            [
                self.alert.check_input(self.aoi_model.name, cm.error.no_aoi),
                self.alert.check_input(self.model.start, cm.error.no_start),
                self.alert.check_input(self.model.end, cm.error.no_end),
                self.alert.check_input(self.model.vegetation_index, cm.error.no_vi),
                self.alert.check_input(self.model.trajectory, cm.error.no_traj),
                self.alert.check_input(self.model.lceu, cm.error.no_lceu),
                self.alert.check_input(self.model.sensors, "no sensors"),
            ]
        ):
            return
        # check if the custom land covers are different or not
        if self.model.start_lc or self.model.end_lc:
            diff_lc = None if self.model.start_lc == self.model.end_lc else True
            if not self.alert.check_input(
                diff_lc,
                cm.select_lc.diff_land_cover,
            ):
                return
        # check if the land cover pixels and codes from the input matrix are same or not (exact match)
        if self.model.start_lc and self.model.end_lc and self.model.lc_pixel_check:
            lc_check_pixels = (
                None
                if set(self.model.lc_codelist_start)
                != set(cs.custom_lc_values(self.model.start_lc))
                or set(self.model.lc_codelist_end)
                != set(cs.custom_lc_values(self.model.end_lc))
                else True
            )
            if not self.alert.check_input(
                lc_check_pixels, cm.select_lc.not_proper_code
            ):
                return

        # check if the land cover pixels and codes from the input matrix are same or not (exact match)
        if self.model.start_lc and self.model.end_lc and not self.model.lc_pixel_check:
            lc_subset_check_pixels = (
                True
                if (
                    (set(cs.custom_lc_values(self.model.start_lc))).issubset(
                        set(self.model.lc_codelist_start)
                    )
                )
                and (
                    (set(cs.custom_lc_values(self.model.end_lc))).issubset(
                        set(self.model.lc_codelist_end)
                    )
                )
                else None
            )
            if not self.alert.check_input(
                lc_subset_check_pixels, cm.select_lc.not_proper_code_subset
            ):
                return
        # check if the input matrix contains proper values/atrributes or not
        if self.model.start_lc and self.model.end_lc and self.model.custom_matrix_file:
            check_min_max_error = (
                None
                if min(self.model.lc_codelist_start) < 10
                or max(self.model.lc_codelist_start) > 99
                else True
            )
            check_transition_code_error = (
                None if {1, 0, -1} != set(self.model.trans_matrix_flatten) else True
            )
            check_lc_class_mismatch = (
                None
                if set(self.model.lc_classlist_start)
                != set(self.model.lc_classlist_end)
                else True
            )
            if not all(
                [
                    self.alert.check_input(
                        check_min_max_error, cm.select_lc.min_max_error
                    ),
                    self.alert.check_input(
                        check_transition_code_error, cm.select_lc.transition_code_error
                    ),
                    self.alert.check_input(
                        check_lc_class_mismatch, cm.select_lc.lc_class_mismatch
                    ),
                ]
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
        pivot_dflc = dflc.pivot(index="landcover", columns="Indicator 15.3.1")["Area"]

        # create the diagrams
        self.result_tile.sankey_plot.clear_output()
        self.result_tile.bar_plot.clear_output()

        with plt.style.context("dark_background"):
            with self.result_tile.sankey_plot:
                fig, ax = cs.sankey(
                    df=df, colorDict=self.model.lc_color, aspect=4, fontsize=12
                )
                fig.set_facecolor((0, 0, 0, 0))
                plt.show()

            with self.result_tile.bar_plot:
                fig, ax = cs.barh_plot(
                    df=pivot_dflc,
                    color=cp.legend,
                    title=f"Distribution of area by land cover ({self.model.lc_year_start_esa})",
                )
                ax.set_facecolor((0, 0, 0, 0))
                fig.set_facecolor((0, 0, 0, 0))
                plt.show()

        # save the figures by default
        pattern = str(result_dir / f"{self.aoi_model.name}_{self.model.folder_name()}")
        fig, ax = cs.sankey(df=df, colorDict=self.model.lc_color, aspect=4, fontsize=12)
        fig.savefig(f"{pattern}_lc_transition.png", dpi=200)
        plt.close()
        fig, ax = cs.barh_plot(
            df=pivot_dflc,
            color=cp.legend,
            title=f"Distribution of area by land cover ({self.model.lc_year_start_esa})",
        )
        fig.savefig(f"{pattern}_area_distribution.png")
        plt.close()

        # export the legend by default
        cs.export_legend(
            f"{pattern}_indicator_legend.png", cp.legend, "Indicator Status"
        )
        cs.export_legend(
            f"{pattern}_lc_legend.png", self.model.lc_color, "Land Cover class"
        )
        df.to_csv(f"{pattern}_lc_transition.csv", index=False)

        # release the download btn
        self.result_tile.btn.disabled = False
        self.zonal_stats_tile.btn.disabled = False

        return

    def _sensor_bind(self, change):
        """manually update the value of the model as the observe is not triggered"""

        self.model.sensors = self.sensor_select.v_model.copy()

        # check it the VI can still be used
        self._update_vegetation_index()
        # hide the vegetation index and trajectory options in case of MODIS NPP data
        self._hide_vi_n_trend()

        return

    def _display_custom_lc_file_selection(self, change):
        """Show hide the lc custom matrix file selection widget"""
        v_model = change["new"]
        if v_model == 1:
            self.custom_matrix_file.show()
            self.default_lc_matrix_bool.hide()
        else:
            self.custom_matrix_file.v_model = ""
            self.custom_matrix_file.hide()
            self.default_lc_matrix_bool.show()
        return

    def _display_default_matrix(self, change):
        """Show hide the lc default matrix file selection widget"""
        v_model = change["new"]
        if v_model == 1:
            self._transition_matrix.show()
            self.custom_lc_matrix_bool.hide()

        else:
            self._transition_matrix.hide()
            self.custom_lc_matrix_bool.show()

    def _update_vegetation_index(self):
        """disable the MSVI2 vegetation option in case of Derived VI Landsat * sensor/s"""

        is_derived = any(
            [s.startswith("Derived VI") for s in self.sensor_select.v_model]
        )
        tmp_items = self.vegetation_index.items.copy()
        next(i for i in tmp_items if i["value"] == "msvi")["disabled"] = is_derived
        self.vegetation_index.items = []
        self.vegetation_index.items = tmp_items
        self.vegetation_index.v_model = tmp_items[0]["value"]

        return

    def _hide_vi_n_trend(self):
        if "Terra NPP" in self.sensor_select.v_model:
            self.vegetation_index.hide()
            self.trajectory.hide()
        else:
            self.vegetation_index.show()
            self.trajectory.show()
