import ipyvuetify as v

from component import parameter as pm
from component.message import cm


class MatrixInput(v.Html):
    VALUES = {
        "I": (1, v.theme.themes.dark.success),
        "S": (0, v.theme.themes.dark.primary),
        "D": (-1, v.theme.themes.dark.error),
    }

    def __init__(self, line, column, model, default_value, output):
        # get the io for dynamic modification
        self.model = model

        # get the line and column of the td in the matrix
        self.column = column
        self.line = line

        # get the output
        self.output = output

        self.val = v.Select(
            dense=True,
            color="white",
            items=[*self.VALUES],
            class_="ma-1",
            v_model=default_value,
        )

        super().__init__(
            style_=f"background-color: {v.theme.themes.dark.primary}",
            tag="td",
            children=[self.val],
        )

        # connect the color to the value
        self.val.observe(self.color_change, "v_model")

    def color_change(self, change):
        val, color = self.VALUES[change["new"]]

        self.style_ = f"background-color: {color}"
        self.model.transition_matrix[self.line][self.column] = val

        self.output.add_msg(cm.matrix_changed)

        return


class TransitionMatrix(v.SimpleTable):
    CLASSES = [*pm.lc_color]

    DECODE = {1: "I", 0: "S", -1: "D"}

    def __init__(self, model, output):
        # create a header
        header = [
            v.Html(
                tag="tr",
                children=(
                    [v.Html(tag="th", children=[""])]
                    + [v.Html(tag="th", children=[class_]) for class_ in self.CLASSES]
                ),
            )
        ]

        # create a row
        rows = []
        for i, baseline in enumerate(self.CLASSES):
            inputs = []
            for j, target in enumerate(self.CLASSES):
                # create a input with default matrix value
                default_value = self.DECODE[pm.default_trans_matrix[i][j]]
                matrix_input = MatrixInput(i, j, model, default_value, output)
                matrix_input.color_change({"new": default_value})

                input_ = v.Html(tag="td", class_="ma-0 pa-0", children=[matrix_input])
                inputs.append(input_)

            row = v.Html(
                tag="tr", children=([v.Html(tag="th", children=[baseline])] + inputs)
            )
            rows.append(row)

        # create the simple table
        super().__init__(children=[v.Html(tag="tbody", children=header + rows)])
