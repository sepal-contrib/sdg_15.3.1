import time

import rasterio as rio
from rasterio.merge import merge
from matplotlib.colors import to_rgba
from matplotlib import pyplot as plt

from component.message import cm
from component import parameter as pm
from .gdrive import gdrive


def digest_tiles(filename, result_dir, output, tmp_file):
    if tmp_file.is_file():
        output.add_live_msg(cm.download.file_exist.format(tmp_file), "warning")
        time.sleep(2)
        return

    drive_handler = gdrive()
    files = drive_handler.get_files(filename)

    # if no file, it means that the download had failed
    if not len(files):
        raise Exception(cm.gdrive.error.no_file)

    drive_handler.download_files(files, result_dir)

    pathname = f"{filename}*.tif"

    files = [file for file in result_dir.glob(pathname)]

    # run the merge process
    output.add_live_msg(cm.download.merge_tile)

    # manual open and close because I don't know how many file there are
    sources = [rio.open(file) for file in files]

    data, output_transform = merge(sources)

    out_meta = sources[0].meta.copy()
    out_meta.update(nodata=0)
    out_meta.update(
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        transform=output_transform,
        compress="lzw",
    )

    # create a colormap
    colormap = {}
    for i, color in enumerate(pm.legend.values()):
        color = tuple(int(c * 255) for c in to_rgba(color))
        colormap[i + 1] = color

    with rio.open(tmp_file, "w", **out_meta) as dest:
        dest.write(data)
        dest.write_colormap(1, colormap)

    # manually close the files
    [src.close() for src in sources]

    # delete local files
    [file.unlink() for file in files]

    return


def export_legend(filename, colors, title):
    """
    Create a color list and display it in a png image.

    Args:
        filename (pathlib.Path); the path where to save the file
        colors (dict): the color palette to create. It should use the following format: {classname: hex_color, ...}

    Return:
        (pathlib.Path) the filename
    """

    # create a color list
    color_map = [*colors.values()]

    columns = ["entry"]
    rows = [" " * 10 for i in range(len(colors))]  # trick to see the first column
    cell_text = [[name] for name in colors]

    fig, ax = plt.subplots(1, 1, figsize=[6.4, 8.6])

    # remove the graph box
    ax.axis("tight")
    ax.axis("off")

    # set the tab title
    ax.set_title(title)

    # create the table
    the_table = ax.table(
        colColours=[to_rgba("lightgrey")],
        cellText=cell_text,
        rowLabels=rows,
        colWidths=[0.4],
        rowColours=color_map,
        colLabels=columns,
        loc="center",
    )
    the_table.scale(1, 1.5)

    # save & close
    plt.savefig(filename)
    plt.close()

    return
