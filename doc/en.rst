SDG 15.3.1
==========

SDG Indicator 15.3.1 measures the proportion of land that is degraded
over total land area. It is part of goal 15 which promotes “Life on Land”
and target 15.3 states: ‘By 2030, combat desertification, restore
degraded land and soil, including land affected by desertification,
drought and floods, and strive to achieve a land degradation–neutral
world.’

This module allows generating data for reporting on SDG indicator 15.3.1. The SEPAL SDG indicator module follows SDG `good practice guidance version 2 <https://www.unccd.int/sites/default/files/documents/2021-09/UNCCD_GPG_SDG-Indicator-15.3.1_version2_2021.pdf>`__. 

The methodology for SDG 15.3.1 module for GPG v1 (`good practice guidance from UNCCD on SDG 15.3.1 <https://prais.unccd.int/sites/default/files/helper_documents/4-GPG_15.3.1_EN.pdf>`__) was implemented in consultation with the `trends.earth <https://trends.earth/docs/en/index.html>`__ team and `Conservation International <https://www.conservation.org>`__.

Methodology
-----------

What is Land degradation?
^^^^^^^^^^^^^^^^^^^^^^^^^

The UNCCD defines land degradation as “\ *the reduction or loss of the
biological or economic productivity and complexity of rain-fed cropland,
irrigated cropland, or range, pasture, forest and woodlands resulting
from a combination of pressures, including land use and management
practices”* (`UNCCD 1994, Article
1 <https://www.unccd.int/sites/default/files/relevant-links/2017-01/UNCCD_Convention_ENG_0.pdf>`__).
This definition was adopted for the SDG 15.3.1

UNCCD Good Practice Guidelines
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The first version was issued in 2017. A revised version is issued in
2021. The module is based on the latest version (version 2) of the document.

Approach
""""""""

Under the definition adopted by UNCCD, the extent of land degradation
for reporting on SDG Indicator 15.3.1 is calculated as a binary -
degraded/not degraded - quantification using its three sub-indicators:

-  Trends in land cover

-  Trends in land productivity, and

-  Trends in carbon stocks (above and below ground), currently
   represented by soil organic carbon (SOC) stocks

Essentially, any significant reduction or negative change in one of the
three sub-indicators is considered to comprise land degradation. That
means the results of the sub-indicators are integrated using the one out
all out statistical principle.

Sub-indicators
##############

Productivity
++++++++++++

Land productivity cycles exhibit phases over time, a continuous decrease
in productivity for a long time indicate potential degradation in land
productivity.

Three matrices are used to detect such changes in productivity:

Productivity trend
     

It measures the trajectory of changes in productivity over the long term.

The `Mann–Kendall <https://en.wikipedia.org/wiki/Kendall_rank_correlation_coefficient>`__ trend test is used to describe the monotonic trend or
trajectory (increasing or decreasing) of the productivity for a given
time period.

To identify the scale and direction of the trend a five-level scale is
proposed:

-  Z score < -1.96 = Degrading, as indicated by a significant decreasing
   trend

-  Z score < -1.28 AND ≥ -1.96 = Potentially Degrading

-  Z score ≥ -1.28 AND ≤ 1.28 = No significant change

-  Z score > 1.28 AND ≤ 1.96 = Potentially Improving, or

-  Z score > 1.96 = Improving, as indicated by a significant increasing
   trend

The area of the lowest negative z-score level (< -1.96) is considered
degraded, the area between z-score -1.96 to 1.96 is considered stable and the 
area above 1.96 is considered improved for calculating the sub-indicator.

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/trend_z.svg
    :alt: trend z score

Productivity state
     

The state represents the level of productivity in a land unit compared to
the historical observations of productivity for that land unit over
time. The mean and standard deviations are calculated as follows:

.. math::

   \mu = \frac{\sum_{n-15}^{n-3}x_n}{13} \\

   \sigma = \sqrt{\frac{\sum_{n-15}^{n-3}(x_n-\mu)^2}{13}}

Where, :math:`x` is the productivity and n is the year of analysis.

The mean productivity of the current period is given as:

.. math:: \bar{x} = \frac{\sum_{n-2}^nx_n}{3}

and the :math:`z` score is given as

.. math:: z =\frac{\bar{x}-\mu}{\frac{\sigma}{\sqrt{3}}}

The five-level stats are as follows:

-  Z score < -1.96 = Degraded, showing a significantly

   lower mean in the recent years compared to the longer term

-  Z score < -1.28 AND ≥ -1.96 = At risk of degrading

-  Z score ≥ -1.28 AND ≤ 1.28 = No significant change

-  Z score > 1.28 AND ≤ 1.96 = Potentially Improving

-  Z score > 1.96 = Improving, as indicated by a significantly higher
   mean in recent years compared to the longer term.
   


The area of the lowest negative z-score level (< -1.96) is considered degraded, 
the area between z-score -1.96 to 1.96 is considered stable and the area above 
1.96 is considered improved for calculating the sub-indicator.

Productivity performance
           

Productivity Performance indicates the level of local plant productivity
relative to other regions with similar productivity potential.

The maximum productivity index (:math:`$NPP_max$`) value (90:sup:`th` percentile)
observed within the simillar ecoregion is campared the observed
productivty value (observed NPP). It is given as:

.. math:: \text{performance} = \frac{NPP_{observed}}{NPP_{max}}

The pixels with an NPP (vegetation index) less than 0.5 of the :math:`$NPP_max$`
is considered as degraded.

Either of the following look-up tables can be used to calculate the sub-indicator:

Look-up table to combine productivity metrics

+------------+------------+----------------+---------------+---------------+
|  Trend     | State      | Performance    | Productivity sub-indicator    |
+------------+------------+----------------+---------------+---------------+
|            |            |                | GPG version 1 | GPG version 1 |
+============+============+================+===============+===============+
| Degrdaded  |  Degrdaded |  Degrdaded     | Degrdaded     |  Degrdaded    |
+------------+------------+----------------+---------------+---------------+
| Degrdaded  |  Degrdaded |  Not degrdaded | Degrdaded     |  Degrdaded    |
+------------+------------+----------------+---------------+---------------+
| Degrdaded  |  Stable    |  Degrdaded     | Degrdaded     |  Degrdaded    |
+------------+------------+----------------+---------------+---------------+
| Degrdaded  |  Stable    |  Not degrdaded | Degrdaded     |  Stable       |
+------------+------------+----------------+---------------+---------------+
| Degrdaded  |  Improved  |  Degrdaded     | Degrdaded     |  Degrdaded    |
+------------+------------+----------------+---------------+---------------+
| Degrdaded  |  Improved  |  Not degrdaded | Degrdaded     |  Degrdaded    |
+------------+------------+----------------+---------------+---------------+
| Stable     |  Degrdaded |  Degrdaded     | Degrdaded     |  Degrdaded    |
+------------+------------+----------------+---------------+---------------+
| Stable     |  Degrdaded |  Not degrdaded | Stable        |  Stable       |
+------------+------------+----------------+---------------+---------------+
| Stable     |  Stable    |  Degrdaded     | Stable        |  Degrdaded    |
+------------+------------+----------------+---------------+---------------+
| Stable     |  Stable    |  Not degraded  | Stable        |  Stable       |
+------------+------------+----------------+---------------+---------------+
| Stable     |  Improved  |  Degraded      | Stable        |  Stable       |
+------------+------------+----------------+---------------+---------------+
| Stable     |  Improved  |  Not degraded  | Stable        |  Stable       |
+------------+------------+----------------+---------------+---------------+
| Improved   |  Degraded  |  Degraded      | Degraded      |  Degraded     |
+------------+------------+----------------+---------------+---------------+
| Improved   |  Degrdaded |  Not degrdaded | Improved      |  Improved     |
+------------+------------+----------------+---------------+---------------+
| Improved   |  Stable    |  Degraded      | Improved      |  Improved     |
+------------+------------+----------------+---------------+---------------+
| Improved   |  Stable    |  Not degraded  | Improved      |  Improved     |
+------------+------------+----------------+---------------+---------------+
| Improved   |  Improved  |  Degraded      | Improved      |  Improved     |
+------------+------------+----------------+---------------+---------------+
| Improved   |  Improved  |  Not degraded  | Improved      |  Improved     |
+------------+------------+----------------+---------------+---------------+


.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/look-up-table.svg
    :alt: Look up table


Available Dataset: 
                  

Sensors : MODIS, Landsat 4, 5, 7 and 8, Sentinel 2

NPP metric: NDVI, EVI and MSVI

Land cover
++++++++++


The land cover indicator is based on transitions of land cover from the initial year to the final year. A transition matrix is used to mark the transition as degraded, stable or improved. A default matrix with predefined transition statuses is given based on IPCC classes. The matrix can be customised based on context and local settings. 

Default land cover dataset: ESA CCI land cover


Transition matrix for custom land cover legends

A custom transition matrix can be used in combination with the custom land cover legend. The matrix is a comma-separated value(.csv) file and needs to be in the following format:

The first two columns, excluding the first two cells (:math:`a_{31}...a_{n1} \text{and } a_{32}...a_{n2}` ), must contain class labelling and pixel values for the initial land cover respectively.
The first two rows, excluding the first two cells, (:math:`a_{13}...a_{1n} \text{and } a_{23}...a_{2n}` ) must contain class labelling and pixel values for the final land cover respectively. The rest of the higher indexed cells :math:`\left(\left[\begin{matrix}a_{33}&\cdots&a_{3n}\\\vdots&\ddots&\vdots\\2_{n3}&\cdots&3_{nn}\end{matrix} \right]\right)` must contain a transition matrix. Cells :math:`a_{11},a_{12},a_{21}, \text{and } a_{22}` can be used to store some metadata. Use 1 to denote improved transitions, 0 for stable and -1 for degraded transitions.

.. math::
    \mathbf{A} = \left[ \begin{matrix}%
    a_{11}&a_{12}&a_{13}&\cdots&a_{1n}\\
    a_{21}&a_{22}&a_{23}&\cdots&a_{2n}\\
    a_{31}&a_{32}&a_{33}&\cdots&a_{3n}\\
    \vdots&\vdots&\vdots&\ddots&\vdots\\
    a_{n1}&a_{n2}&a_{n3}&\cdots&a_{nn}\end{matrix}\right]


An example of a custom transition matrix:

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/ipccsx_matrix_explained.svg
    :alt: custom transition matrix

Soil Organic Carbon
+++++++++++++++++++

Based on the IPCC methodology (Chapter 6).


Final indicator
+++++++++++++++

The final indicator is based on the one out all out the principle.

Users Guide
-----------

Select AOI
^^^^^^^^^^

The SDG 15.3.1 will be calculated based on the user inputs. The first mandatory input is the Area Of Interest (AOI). In this step you’ll have the possibility to choose from a predefined list of administrative layers or use your datasets, the available options are:

**Predefined layers**

-   Country/province
-   Administrative level 1
-   Administrative level 2

**Custom layers**

-   Vector file
-   Drawn shapes on the map
-   Google Earth Engine Asset

After selecting the desired area, click over :guilabel:`Select these inputs` and the map shows up your selection.

.. note::

    You can only select one area of interest. In some cases, depending on the input data you could run out of resources in GEE.
    
.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/aoi_selection.png
    :alt: AOI selection
    
Parameters
""""""""""

To run the computation of SDG 15.3.1, several parameters need to be set. Please read the `Good practice guidelines <https://www.unccd.int/sites/default/files/documents/2021-09/UNCCD_GPG_SDG-Indicator-15.3.1_version2_2021.pdf>`__ to better understand the parameters required to calculate SDG 15.3.1 indicator and it's sub-indicators.

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/parameters.png
    :alt: parameters

Mandatory parameters
####################

-   **Dates**: They are set in years and need to be in the correct order. The **end date** that you select will change the list of available sensors. You won't be able to choose sensors that were not launched by the **end date**

-   **Sensors**: After selecting the dates, all the available sensors within the timeframe will be available. You can deselect or re-select any sensor you want. The default value is set to all the Landsat satellites available within the selected timeframe.

.. note::
   
        Some of the sensors are incompatible with each other. Thus selecting Landsat, MODIS or Sentinel dataset in the **sensors** dropdown will deselect the others.
        
-   **Vegetation index**: THe vegetation index will be used to compute the trend trajectory, default to *NDVI*.

-   **trajectory**: There are 3 options available to calculate the productivity trend that describes the trajectory of change, default to *productivity (VI) trend*.

-   **land ecosystem functional unit**: default to *Global Agro-Environmental Stratification (GAES)*, other available options are:

    - `Global Agro Ecological Zones (GAEZ), historical AEZ with 53 classes <https://gaez.fao.org/>`__ 
    - `World Ecosystem <https://doi.org/10.1016/j.gecco.2019.e00860>`__
    - `Global Homogeneous Response Units <https://doi.pangaea.de/10.1594/PANGAEA.775369>`__
    - Calculate based on the land cover (`ESA CCI <https://cds.climate.copernicus.eu/cdsapp#!/dataset/satellite-land-cover?tab=overview>`__) and soil texture (`ISRIC <https://www.isric.org/explore/soilgrids>`__)

-   **climate regime**: default to *Per pixel based on global climate data* but you can also use a fixed value everywhere using a predefined climate regime in the dropdown menu or select a custom value on the slider

Advanced parameters
###################

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/advanced_parameters.png
    :alt: advanced parameters

Productivity related parameters
+++++++++++++++++++++++++++++++

Assessment periods for all the metrics can be specified individually. Keep them blank to use the Start and End dates for the respective metric.

.. note::
    
     If you only specify either the start or the end year of a particular metric, the module will ignore the value.

The default productivity look-up table is set to GPG version 2. We could also select GPG version 1. Please refer to the approach section for the tables.  Please read section 4.2.5 of the `GPG version 2 <https://www.unccd.int/sites/default/files/documents/2021-09/UNCCD_GPG_SDG-Indicator-15.3.1_version2_2021.pdf>`__ to know more about the look-up table.

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/prod_params.png
    :alt: productivity parameters


Land cover related parameters:
++++++++++++++++++++++++++++++

Water body data

The default water body data is set to JRC water body seasonality data with a seasonality of 8 months. An :code:`ee.Image` can be used for the water body data with a pixel value greater than equal to 1. Waterbody can be extracted from the land cover data by specifying the corresponding pixel value. To use the water body from ESA CCI land cover data, set the slider to 70.


.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/water_body.png
    :alt: water body


The default land cover is set to the ESA CCI land cover data. The tool will use the CCI land cover system of the **start date** and the **end date**. These land cover images will be reclassified into the IPCC classification system and used to compute the land cover sub-indicator. However, You can specify your data for the start and the end land cover data. Provide the :code:`ee.Image` asset name and the band that need to be used and the default dataset will be replaced in the computation by your custom data. 

.. note::

     If would like to use the default land cover transition matrix, the custom dataset needs to be classified in the IPCC classification system. Please refer to :ref:`sdg_reclassify` to know how to reclassify your local dataset into a different classification system.
    
To compute the land cover sub-indicator with the IPCC classes, the user can modify the default transition matrix. Based on the user's local knowledge of the conditions in the study area and the land degradation process occurring there, use the table below to identify which transitions correspond to degradation (D), improvement (I), or no change in terms of land condition (S).

The rows stand for the initial classes and the columns for the final classes.

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/default_matrix.png
    :alt: water body


    
Custom land cover transition matrix

If you would like to use a custom land cover transition matrix, select the :guilabel:`Yes` radio button and select the CSV file. Use `this matrix <https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/utils/ipccsx_matrix.csv>`__ as a template to prepare a matrix for your land cover map.


SOC related parameters:
+++++++++++++++++++++++
    
Launch the computation
######################

Once all the parameters are set you can run the analysis by clicking on :guilabel:`Load the indicators`.
It takes time to calulate all the sub-indicator. Look at the Alert at the bottom of the panel that displays the current state of analysis.

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/validate_data.png
    :alt: validate data


Results
"""""""

The results are displayed to the end user in the next panel. On the left the user will find the transition and the distribution charts and on the right, an interactive map where every indicator and sub-indicators layers are displayed.

click on the :guilabel:`donwload` button to exort all the layers, charts and tables to your SEPAL folder. 

The results are gathered in the :code:`module_results/sdg_indicators/` folder. In this folder a folder is set for each AOI (e.g. :code:`SGP/` for Singapore) and within this folder results are grouped by run computation. the title of the folder reflect the parameters following this symbology: :code:`<start_year>_<end_year>_<satellites>_<vegetation index>_<lc units>_<custom LC>_<climate>`.

.. note:: 

    As an example for computation used in this documentation, the results were saved in : :code:`module_results/sdg_indicator/SGP/2015_2019_modis_ndvi_calculate_default_cr0/`

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/results.png
    :alt: validate data
    
.. note:: 

    the results are interactive, don't hesitate to interact with both the charts and the map layers using the widgets.
    
    .. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/results_interaction.gif
        :alt: result interaction
        
Transition graph 
^^^^^^^^^^^^^^^^

This chart is the `Sankey diagram <https://en.wikipedia.org/wiki/Sankey_diagram>`__ of the land cover transition between baseline and target year. The color is corresponding to the initial class.

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/transition_graph.png
    :alt: transiton graph
    :width: 40%
    :align: center

Distribution graph 
^^^^^^^^^^^^^^^^^^

This chart displays the distribution of the SDG 15.3.1 indicator on each classes of the input land cover.

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/distribution_graph.png
    :alt: distribution chart
    :width: 40%
    :align: center

Interactive map
^^^^^^^^^^^^^^^

Are displayed on the map the following indicators: 

-   SDG 15.3.1
-   land cover sub-indicator
-   trajectory sub-indicator
-   performance sub-indicator

These indicator are all displayed using the same symbology (Improved: blue, stable: beige, degraded: red).

The tool also display the land cover maps from baseline and target years using the UNCCD symbology.

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/lc_map.png
    :alt: lc_map
    :width: 80%
    :align: center


.. sdg_reclassify:

Reclassify
""""""""""

.. warning:: 

    To reclassify a land_cover map, this map need to be available to the user as a :code:`ee.Image` in GEE.

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/reclassification.png
    :alt: reclassification


In order to use a custom land cover map, the user needs to first reclassify to a classification system. For the default IPCC classification system,  values between 10 to 70 are used to describe the following land cover classes: This is the 

#. forest
#. grassland
#. cropland
#. wetland
#. artificial
#. bareland
#. water

This is the default matrix. 

First select the asset in the combobox. It will be part of the dropdown value if the asset is part of the user's asset list. If that's not the case simply set the name of the asset in the TextField.


Then select the band that will be reclassified.

For a custom legend/classification system, upload a matrix with first clomun as pixel values, second column as class label and third as hex colour code.


.. note::

    This band need to be a categorical band, the reclassification sytem won't work with continuous values.
    
Click on :guilabel:`get table`. This will generate a table with all the categorical values of the asset. In the second column the user can set the destination value. 

.. tip::

    - If the destination class is not set, the class will be interpreded as no_ata i.e. 0;
    - click on :guilabel:`save` to save the reclassification matrix. It's useful when the baseline and target map are in the same classification system;
    - click on :guilabel:`import` to import a previously saved reclassification matrix.
    
    
Click on :guilabel:`reclassify` to export the map in GEE using the IPCC classification system. The export can be monitored in GEE. 

The following GIF will show you the full reclassification process with an simple example.

.. image:: https://raw.githubusercontent.com/sepal-contrib/sdg_15.3.1/master/doc/img/reclassify_demo.gif
    :alt: reclassification demo

