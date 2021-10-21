from matplotlib import pyplot as plt

from component import parameter as cp


def bar_plot(df):

    # create the figure
    fig, ax = plt.subplots(figsize=(10, 9))

    # plot the dataframe
    df.plot.bar(
        rot=0,
        color=cp.legend,
        ax=ax,
        edgecolor="black",
        fontsize=12,
    )

    # fix the design of the plot
    ax.set_xlabel("Land cover")
    ax.set_yscale("log")
    ax.set_ylabel("Area in ha")
    ax.set_title("Distribution of area by land cover type", fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    return fig, ax
