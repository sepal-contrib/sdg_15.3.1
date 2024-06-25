import time

import ee

from component.message import cm


# messages
STATUS = "Status : {0}"


def wait_for_completion(task_descripsion, output):
    """Wait until the selected process are finished. Display some output information

    Args:
        task_descripsion ([str]) : name of the running tasks
        widget_alert (v.Alert) : alert to display the output messages

    Returns: state (str) : final state
    """
    state = "UNSUBMITTED"
    while not (state == "COMPLETED" or state == "FAILED"):
        output.add_live_msg(cm.gee.status.format(state))
        time.sleep(5)

        # search for the task in task_list
        for task in task_descripsion:
            current_task = search_task(task)
            state = current_task.state
            if state == "RUNNING":
                break

    return state


def search_task(task_descripsion):
    """Search for the described task in the user Task list return None if nothing is find

    Args:
        task_descripsion (str): the task descripsion

    Returns
        task (ee.Task) : return the found task else None
    """

    tasks_list = ee.batch.Task.list()
    current_task = None
    for task in tasks_list:
        if task.config["description"] == task_descripsion:
            current_task = task
            break

    return current_task
