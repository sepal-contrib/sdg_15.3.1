from traitlets import link, CBool, Int
import ipyvuetify as v
import sepal_ui.sepalwidgets as sw


class BoolQuestion(v.Flex, sw.SepalWidget):

    v_model = CBool(False).tag(sync=True)

    def __init__(self, question, *args, **kwargs):

        super().__init__(*args, **kwargs)

        bool_radios = v.RadioGroup(
            row=True,
            v_model=self.v_model,
            children=[
                v.Radio(label="No", value=False),
                v.Radio(label="Yes", value=True),
            ],
        )

        link((bool_radios, "v_model"), (self, "v_model"))

        self.children = [v.Html(tag="h3", children=[question]), bool_radios]
