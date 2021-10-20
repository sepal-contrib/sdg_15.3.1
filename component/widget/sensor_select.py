import ipyvuetify as v

from component import parameter as pm
from component.message import ms


class SensorSelect(v.Select):
    def __init__(self):

        super().__init__(
            items=[],
            label=ms._15_3_1.sensor_lbl,
            multiple=True,
            v_model=[],
            chips=True,
            deletable_chips=True,
        )

    def update_sensors(self, change):

        # deselect all
        self.v_model = []

        # define the offset that should be used based on the year in the sensors list
        if change["new"] >= 2015:  # launch of Sentinel 2
            last_sat = 7
        elif change["new"] >= 2013:  # launch of Landsat 8
            last_sat = 6
        elif change["new"] >= 1999:  # launch of landsat 7 and MODIS
            last_sat = 5
        elif change["new"] >= 1984:  # launch of landsat 5
            last_sat = 2
        else:
            last_sat = 1

        # get the availabel sats
        items = [*pm.sensors][:last_sat]

        # change sensor items
        self.items = sorted(items)

        # remove the non landsat satellites from the default values
        no_default_list = ["Sentinel 2", "MODIS MOD13Q1", "MODIS NPP"]
        self.v_model = [i for i in items if i not in no_default_list]

        return
