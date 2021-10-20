# -*- coding: utf-8 -*-
"""
Produces Sankey Diagrams with matplotlib to show the transition in land cover.
adopted from : Sankey by  Anneya Golob & marcomanz & pierre-sassoulas & jorwoods
from https://github.com/anazalea/pySankey
"""

from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def sankey(df, colorDict=None, aspect=4, rightColor=False, fontsize=14):
    """
    Sankey Diagram for showing land cover transitions

    Inputs:
        df = pandas dataframe with first column as left, second column as right and third colum as leftWeight
        colorDict = Dictionary of colors to use for each label
            {'label':'color'}
        aspect = vertical extent of the diagram in units of horizontal extent
        rightColor = If true, each strip in the diagram will be be colored
                    according to its left label
    Ouput: fig, ax
    """
    left = df[df.columns[0]]
    right = df[df.columns[1]]
    leftWeight = df["Area"]
    rightWeight = []

    leftLabels = []
    rightLabels = []
    # Check weights
    if len(leftWeight) == 0:
        leftWeight = np.ones(len(left))

    if len(rightWeight) == 0:
        rightWeight = leftWeight

    fig, ax = plt.subplots(figsize=(10, 10))

    # Create Dataframe
    if isinstance(left, pd.Series):
        left = left.reset_index(drop=True)
    if isinstance(right, pd.Series):
        right = right.reset_index(drop=True)
    dataFrame = pd.DataFrame(
        {
            "left": left,
            "right": right,
            "leftWeight": leftWeight,
            "rightWeight": rightWeight,
        },
        index=range(len(left)),
    )

    if len(dataFrame[(dataFrame.left.isnull()) | (dataFrame.right.isnull())]):
        raise ValueError("Sankey graph does not support null values.")

    # Identify all labels that appear 'left' or 'right'

    # Identify left labels
    if len(leftLabels) == 0:
        leftLabels = pd.Series(dataFrame.left.unique()).unique()

    # Identify right labels
    if len(rightLabels) == 0:
        rightLabels = pd.Series(dataFrame.right.unique()).unique()

    # If no colorDict given, make one
    if colorDict is None:
        raise ValueError("specify a colour palette")

    # Determine widths of individual strips
    ns_l = defaultdict()
    ns_r = defaultdict()
    for leftLabel in leftLabels:
        leftDict = {}
        rightDict = {}
        for rightLabel in rightLabels:
            leftDict[rightLabel] = dataFrame[
                (dataFrame.left == leftLabel) & (dataFrame.right == rightLabel)
            ].leftWeight.sum()
            rightDict[rightLabel] = dataFrame[
                (dataFrame.left == leftLabel) & (dataFrame.right == rightLabel)
            ].rightWeight.sum()
        ns_l[leftLabel] = leftDict
        ns_r[leftLabel] = rightDict

    # Determine positions of left label patches and total widths
    leftWidths = defaultdict()
    for i, leftLabel in enumerate(leftLabels):
        myD = {}
        myD["left"] = dataFrame[dataFrame.left == leftLabel].leftWeight.sum()
        if i == 0:
            myD["bottom"] = 0
            myD["top"] = myD["left"]
        else:
            myD["bottom"] = (
                leftWidths[leftLabels[i - 1]]["top"] + 0.02 * dataFrame.leftWeight.sum()
            )
            myD["top"] = myD["bottom"] + myD["left"]
            topEdge = myD["top"]
        leftWidths[leftLabel] = myD

    # Determine positions of right label patches and total widths
    rightWidths = defaultdict()
    for i, rightLabel in enumerate(rightLabels):
        myD = {}
        myD["right"] = dataFrame[dataFrame.right == rightLabel].rightWeight.sum()
        if i == 0:
            myD["bottom"] = 0
            myD["top"] = myD["right"]
        else:
            myD["bottom"] = (
                rightWidths[rightLabels[i - 1]]["top"]
                + 0.02 * dataFrame.rightWeight.sum()
            )
            myD["top"] = myD["bottom"] + myD["right"]
            topEdge = myD["top"]
        rightWidths[rightLabel] = myD

    # Total vertical extent of diagram
    xMax = topEdge / aspect

    # Draw vertical bars on left and right of each  label's section & print label
    for leftLabel in leftLabels:
        ax.fill_between(
            [-0.02 * xMax, 0],
            2 * [leftWidths[leftLabel]["bottom"]],
            2 * [leftWidths[leftLabel]["bottom"] + leftWidths[leftLabel]["left"]],
            color=colorDict[leftLabel],
            alpha=0.99,
        )
        ax.text(
            -0.05 * xMax,
            leftWidths[leftLabel]["bottom"] + 0.5 * leftWidths[leftLabel]["left"],
            leftLabel,
            {"ha": "right", "va": "center"},
            fontsize=fontsize,
        )
    for rightLabel in rightLabels:
        ax.fill_between(
            [xMax, 1.02 * xMax],
            2 * [rightWidths[rightLabel]["bottom"]],
            2 * [rightWidths[rightLabel]["bottom"] + rightWidths[rightLabel]["right"]],
            color=colorDict[rightLabel],
            alpha=0.99,
        )
        ax.text(
            1.05 * xMax,
            rightWidths[rightLabel]["bottom"] + 0.5 * rightWidths[rightLabel]["right"],
            rightLabel,
            {"ha": "left", "va": "center"},
            fontsize=fontsize,
        )

    # Plot strips
    for leftLabel in leftLabels:
        for rightLabel in rightLabels:
            labelColor = leftLabel
            if rightColor:
                labelColor = rightLabel
            if (
                len(
                    dataFrame[
                        (dataFrame.left == leftLabel) & (dataFrame.right == rightLabel)
                    ]
                )
                > 0
            ):
                # Create array of y values for each strip, half at left value,
                # half at right, convolve
                ys_d = np.array(
                    50 * [leftWidths[leftLabel]["bottom"]]
                    + 50 * [rightWidths[rightLabel]["bottom"]]
                )
                ys_d = np.convolve(ys_d, 0.05 * np.ones(20), mode="valid")
                ys_d = np.convolve(ys_d, 0.05 * np.ones(20), mode="valid")
                ys_u = np.array(
                    50 * [leftWidths[leftLabel]["bottom"] + ns_l[leftLabel][rightLabel]]
                    + 50
                    * [rightWidths[rightLabel]["bottom"] + ns_r[leftLabel][rightLabel]]
                )
                ys_u = np.convolve(ys_u, 0.05 * np.ones(20), mode="valid")
                ys_u = np.convolve(ys_u, 0.05 * np.ones(20), mode="valid")

                # Update bottom edges at each label so next strip starts at the right place
                leftWidths[leftLabel]["bottom"] += ns_l[leftLabel][rightLabel]
                rightWidths[rightLabel]["bottom"] += ns_r[leftLabel][rightLabel]
                ax.fill_between(
                    np.linspace(0, xMax, len(ys_d)),
                    ys_d,
                    ys_u,
                    alpha=0.65,
                    color=colorDict[labelColor],
                )
    ax.axis("off")
    ax.set_title(f"Land cover transitions from {df.columns[0]} to {df.columns[1]}")
    left, width = -0.001, 0.5
    bottom, height = 0.25, 0.5
    right = left + width
    top = bottom + height

    ax.text(
        left,
        0.5 * (bottom + top),
        df.columns[0],
        horizontalalignment="right",
        verticalalignment="center",
        rotation="vertical",
        alpha=0.15,
        fontsize=50,
        transform=ax.transAxes,
    )
    ax.text(
        1.100,
        0.5 * (bottom + top),
        df.columns[1],
        horizontalalignment="right",
        verticalalignment="center",
        rotation="vertical",
        alpha=0.15,
        fontsize=50,
        transform=ax.transAxes,
    )
    # plt.show()
    # plt.savefig("{}.svg".format('sankey'), bbox_inches='tight', dpi=150)
    return (fig, ax)
