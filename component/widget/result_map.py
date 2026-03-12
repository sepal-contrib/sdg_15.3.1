import os
from sepal_ui import mapping as sm
import ipywidgets as widgets
import ipyleaflet
from IPython.display import display


# Built-in legend definitions (extracted from geemap)
BUILTIN_LEGENDS = {
    "NLCD": {
        "11 Open Water": "466b9f",
        "12 Perennial Ice/Snow": "d1def8",
        "21 Developed, Open Space": "dec5c5",
        "22 Developed, Low Intensity": "d99282",
        "23 Developed, Medium Intensity": "eb0000",
        "24 Developed High Intensity": "ab0000",
        "31 Barren Land (Rock/Sand/Clay)": "b3ac9f",
        "41 Deciduous Forest": "68ab5f",
        "42 Evergreen Forest": "1c5f2c",
        "43 Mixed Forest": "b5c58f",
        "51 Dwarf Scrub": "af963c",
        "52 Shrub/Scrub": "ccb879",
        "71 Grassland/Herbaceous": "dfdfc2",
        "72 Sedge/Herbaceous": "d1d182",
        "73 Lichens": "a3cc51",
        "74 Moss": "82ba9e",
        "81 Pasture/Hay": "dcd939",
        "82 Cultivated Crops": "ab6c28",
        "90 Woody Wetlands": "b8d9eb",
        "95 Emergent Herbaceous Wetlands": "6c9fb8",
    }
}

# HTML template for legend (self-contained)
LEGEND_TEMPLATE = """
<div style="position: fixed; 
     bottom: 20px; right: 20px; width: auto; height: auto; 
     border:2px solid grey; z-index:9999; font-size:14px;
     background-color: white;
     ">
  <div style="padding: 10px; font-weight: bold; text-align: center;">
    Legend
  </div>
  <ul style="list-style-type: none; margin: 0; padding: 10px;">
  </ul>
</div>
"""


def rgb_to_hex(rgb):
    """Convert RGB tuple to hex color string.

    Args:
        rgb (tuple): RGB color as tuple of integers (r, g, b)

    Returns:
        str: Hex color string with # prefix
    """
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))


class ResultMap(sm.SepalMap):
    """Extend the classic sepal map to provide 2 legends at the same time"""

    def add_legend(
        self,
        legend_title="Legend",
        legend_dict=None,
        legend_keys=None,
        legend_colors=None,
        position="bottomright",
        builtin_legend=None,
        layer_name=None,
        **kwargs,
    ):
        """Adds a customized legend to the map.

        Args:
            legend_title (str, optional): Title of the legend. Defaults to 'Legend'.
            legend_dict (dict, optional): A dictionary containing legend items as keys
                and color as values. If provided, legend_keys and legend_colors will be
                ignored. Defaults to None.
            legend_keys (list, optional): A list of legend keys. Defaults to None.
            legend_colors (list, optional): A list of legend colors. Defaults to None.
            position (str, optional): Position of the legend. Defaults to 'bottomright'.
            builtin_legend (str, optional): Name of the builtin legend to add to the map.
                Defaults to None.
            layer_name (str, optional): Layer name of the legend to be associated with.
                Defaults to None.
        """
        # Extract kwargs with defaults
        min_width = kwargs.get("min_width", None)
        max_width = kwargs.get(
            "max_width", "300px" if kwargs.get("width") is None else None
        )
        min_height = kwargs.get("min_height", None)
        max_height = kwargs.get(
            "max_height", "400px" if kwargs.get("height") is None else None
        )
        height = kwargs.get("height", None)
        width = kwargs.get("width", None)

        # Set default legend keys if not provided
        if legend_keys is None:
            legend_keys = ["One", "Two", "Three", "Four", "etc"]
        elif not isinstance(legend_keys, list):
            print("The legend keys must be a list.")
            return

        # Process legend colors
        if legend_colors is None:
            legend_colors = [
                "#8DD3C7",
                "#FFFFB3",
                "#BEBADA",
                "#FB8072",
                "#80B1D3",
            ]
        elif not isinstance(legend_colors, list):
            print("The legend colors must be a list.")
            return
        elif all(isinstance(item, tuple) for item in legend_colors):
            try:
                legend_colors = [rgb_to_hex(x) for x in legend_colors]
            except Exception as e:
                print(f"Error converting RGB to hex: {e}")
                return
        elif all((item.startswith("#") and len(item) == 7) for item in legend_colors):
            pass
        elif all((len(item) == 6) for item in legend_colors):
            pass
        else:
            print("The legend colors must be a list of hex colors or RGB tuples.")
            return

        # Handle builtin legends
        if builtin_legend is not None:
            if builtin_legend not in BUILTIN_LEGENDS:
                print(
                    "The builtin legend must be one of the following: {}".format(
                        ", ".join(BUILTIN_LEGENDS.keys())
                    )
                )
                return
            legend_dict = BUILTIN_LEGENDS[builtin_legend]
            legend_keys = list(legend_dict.keys())
            legend_colors = list(legend_dict.values())

        # Handle legend dictionary
        if legend_dict is not None:
            if not isinstance(legend_dict, dict):
                print("The legend dict must be a dictionary.")
                return
            legend_keys = list(legend_dict.keys())
            legend_colors = list(legend_dict.values())
            if all(isinstance(item, tuple) for item in legend_colors):
                try:
                    legend_colors = [rgb_to_hex(x) for x in legend_colors]
                except Exception as e:
                    print(f"Error converting RGB to hex: {e}")
                    return

        # Validate legend keys and colors match
        if len(legend_keys) != len(legend_colors):
            print("The legend keys and values must be the same length.")
            return

        # Validate position
        allowed_positions = ["topleft", "topright", "bottomleft", "bottomright"]
        if position not in allowed_positions:
            print(
                "The position must be one of the following: {}".format(
                    ", ".join(allowed_positions)
                )
            )
            return

        # Build legend HTML
        legend_html = self._build_legend_html(legend_title, legend_keys, legend_colors)

        # Create and add legend widget
        try:
            legend_output_widget = widgets.Output(
                layout={
                    "max_width": max_width,
                    "min_width": min_width,
                    "max_height": max_height,
                    "min_height": min_height,
                    "height": height,
                    "width": width,
                    "overflow": "auto",
                }
            )
            legend_control = ipyleaflet.WidgetControl(
                widget=legend_output_widget, position=position
            )
            legend_widget = widgets.HTML(value=legend_html)
            with legend_output_widget:
                display(legend_widget)

            self.add_control(legend_control)

        except Exception as e:
            raise Exception(f"Error adding legend to map: {e}")

    def _build_legend_html(self, title, keys, colors):
        """Build the HTML string for the legend.

        Args:
            title (str): Legend title
            keys (list): List of legend item labels
            colors (list): List of hex color codes

        Returns:
            str: Complete HTML for the legend
        """
        header = f"""
<div style="position: relative; 
     width: auto; 
     max-width: 150px;
     height: auto; 
     z-index: 9999; 
     font-size: 10px;
     background-color: rgba(255, 255, 255, 0.9);
     color: #333;
     border-radius: 4px;
     padding: 6px;
     box-shadow: 0 1px 5px rgba(0,0,0,0.2);
     ">
  <div style="padding: 3px 0 4px 0; 
              font-weight: bold; 
              font-size: 11px;
              color: #333;
              border-bottom: 1px solid rgba(0,0,0,0.1);
              margin-bottom: 4px;">
    {title}
  </div>
  <ul style="list-style-type: none; 
             margin: 0; 
             padding: 0;">
"""

        content = []
        for key, color in zip(keys, colors):
            # Ensure color has # prefix
            if not color.startswith("#"):
                color = "#" + color
            item = f"""      <li style="margin: 2px 0; 
                   line-height: 14px;
                   display: flex;
                   align-items: center;">
        <span style="background: {color}; 
                     display: inline-block; 
                     width: 12px; 
                     height: 12px; 
                     margin-right: 4px; 
                     border: 1px solid rgba(0,0,0,0.2);
                     border-radius: 2px;
                     flex-shrink: 0;"></span>
        <span style="color: #333; 
                     font-size: 9px;
                     white-space: nowrap;
                     overflow: hidden;
                     text-overflow: ellipsis;">{key}</span>
      </li>
"""
            content.append(item)

        footer = """
  </ul>
</div>

<style>
@media (prefers-color-scheme: dark) {
  .leaflet-container div[style*="z-index: 9999"] {
    background-color: rgba(50, 50, 50, 0.9) !important;
    color: #e0e0e0 !important;
  }
  .leaflet-container div[style*="z-index: 9999"] div {
    color: #e0e0e0 !important;
    border-bottom-color: rgba(255,255,255,0.1) !important;
  }
  .leaflet-container div[style*="z-index: 9999"] span {
    color: #e0e0e0 !important;
  }
  .leaflet-container div[style*="z-index: 9999"] li span:first-child {
    border-color: rgba(255,255,255,0.3) !important;
  }
}

/* Explicit dark theme class support */
.theme--dark div[style*="z-index: 9999"],
.v-application.theme--dark div[style*="z-index: 9999"] {
  background-color: rgba(50, 50, 50, 0.9) !important;
  color: #e0e0e0 !important;
}
.theme--dark div[style*="z-index: 9999"] div,
.v-application.theme--dark div[style*="z-index: 9999"] div {
  color: #e0e0e0 !important;
  border-bottom-color: rgba(255,255,255,0.1) !important;
}
.theme--dark div[style*="z-index: 9999"] span,
.v-application.theme--dark div[style*="z-index: 9999"] span {
  color: #e0e0e0 !important;
}
.theme--dark div[style*="z-index: 9999"] li span:first-child,
.v-application.theme--dark div[style*="z-index: 9999"] li span:first-child {
  border-color: rgba(255,255,255,0.3) !important;
}
</style>
"""

        return header + "".join(content) + footer
