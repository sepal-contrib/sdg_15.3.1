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
            last_sat = 6
        elif change["new"] >= 2013:  # launch of Landsat 8
            last_sat = 5
        elif change["new"] >= 1999:  # launch of landsat 7
            last_sat = 4
        elif change["new"] >= 1984:  # launch of landsat 5
            last_sat = 3
        else:
            last_sat = 2

        # get the availabel sats
        items = [*pm.sensors][:last_sat]

        # change sensor items
        self.items = items

        # change sensor v_model
        items.remove("Sentinel 2")
        items.remove("MODIS MOD13Q1")
        self.v_model = items

        return
