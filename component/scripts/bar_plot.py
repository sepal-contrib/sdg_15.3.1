from matplotlib import pyplot as plt

from component import parameter as cp


def barh_plot(df, color, title):
    # discard no data values
    df = df[["Degraded", "Stable", "Improved"]]
    # convert unit to percentage
    pct = df.div(df.sum(axis=1), axis=0).mul(100).round(2)
    fig, ax = plt.subplots(figsize=(10, 9))

    # plot the dataframe
    pct.plot.barh(stacked=True, color=color, ax=ax, fontsize=12)

    # fix the design of the plot
    ax.set_xlabel("Percentage of area")
    ax.set_xlim(0, 100)
    ax.set_ylabel("Land cover type")
    ax.set_title(title, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.legend(ncol=3, bbox_to_anchor=(1, -0.18), loc="lower right")

    return fig, ax
