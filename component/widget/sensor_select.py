import ipyvuetify as v
from traitlets import observe, Int

from component import parameter as pm
from component.message import ms


class SensorSelect(v.Select):

    update = Int(0).tag(sync=True)

    def __init__(self):

        super().__init__(
            items=[],
            label=ms.sensor_lbl,
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
            last_sat = 8
        elif change["new"] >= 2013:  # launch of Landsat 8
            last_sat = 7
        elif change["new"] >= 1999:  # launch of landsat 7 and MODIS
            last_sat = 6
        elif change["new"] >= 1984:  # launch of landsat 5
            last_sat = 2
        else:
            last_sat = 1

        # get the availabel sats
        items = [*pm.sensors][:last_sat]

        # change sensor items
        self.items = sorted(items)

        # remove the non landsat satellites from the default values
        no_default_list = ["Sentinel 2", "MODIS MOD13Q1", "MODIS MYD13Q1", "Terra NPP"]
        self.v_model = [i for i in items if i not in no_default_list]

        return

    @observe("v_model")
    def _check_sensor(self, change):
        """
        prevent users from mixing landsat, sentinel 2 and  MODIS sensors together
        """

        # exit if its a removal
        if len(change["new"]) <= len(change["old"]):
            return self

        # use positionning in the list as boolean value
        sensors = ["Landsat", "Sentinel", "MODIS", "Terra"]

        # guess the new input
        new_value = list(set(change["new"]) - set(change["old"]))[0]

        other_sensors = [x for x in sensors if x not in new_value]
        if any(i not in new_value for i in other_sensors):
            if any(i in s for s in change["old"] for i in other_sensors):
                self.v_model = [new_value]

        # as we are in a callback the modification we make to the v_model are not triggering
        # the binding. need to be done afterward and/or elsewhere
        self.update += 1

        return self
