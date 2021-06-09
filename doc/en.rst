SDG Indicators
==============

This module allows to generate data for reporting on SDG indicators. The SEPAL SDG indicator module follows SDG best practice guidance, such as the [best practice guidance from UNCCD on SDG 15.3.1.](https://prais.unccd.int/sites/default/files/helper_documents/4-GPG_15.3.1_EN.pdf) The methodology for SDG 15.3.1 was implemented in consultation with the trends.earth team at Conservation International.

Select an AOI
-------------

Using the provided AOI selector, select an AOI of your choice between the different methods available in the tool. We provide 3 administration descriptions (from level 0 to 2) and 3 custom shapes (drawn directly on the map, asset or shapefile). 

.. figure:: https://raw.githubusercontent.com/12rambau/sdg_indicators_module/master/doc/img/aoi_select.png 
    
    aoi selector 
    
.. note::

    If a custom aoi from shape or drawing is selected, you will be able to use it directly and the upload to GEE will be launched in the background
    
Set up parameters
-----------------

Select Date
^^^^^^^^^^^

First you will need to select **start year**, **Start year of the target period** (= end year of the baseline period), and **end year** of the analysis.

.. figure:: https://raw.githubusercontent.com/12rambau/sdg_indicators_module/master/doc/img/select_date.png

    select date

Select sensors
^^^^^^^^^^^^^^

Afetr selecting the date all the available sensors within the timeframe will be available. You can deselect or re-select any sensor you want.

.. figure:: https://raw.githubusercontent.com/12rambau/sdg_indicators_module/master/doc/img/select_sensor.png

    select sensors

Select a trajectory
^^^^^^^^^^^^^^^^^^^

There are three options available to calculate the productivity trend that describe trajectry of change

-   Based on NDVI trend
-   Based on residual trend
-   Trend based on water use efficiency

..  figure:: https://raw.githubusercontent.com/12rambau/sdg_indicators_module/master/doc/img/select_trajectory.png

    select trajectory

Generate a land cover transition matrix
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We need a transition matrix to calculate the degradation that has occurred specifically as a result of land cover change. 
As a transtion is contex specific, you might need to change the transition matrix to suit your objective. You can change the default values just by clicking on a cell.

.. figure:: https://raw.githubusercontent.com/12rambau/sdg_indicators_module/master/doc/img/transition_matrix.png

    generate transition

Select a climate regime
^^^^^^^^^^^^^^^^^^^^^^^

The value of climate resime is required to calculate the SOC change.
You can leave this option to calculate the values using global climate data. Or you can select a predefine value for the entire AOI, or there is also a option avaialble to define a custom value.

.. figure:: https://raw.githubusercontent.com/12rambau/sdg_indicators_module/master/doc/img/cliamte_regime.png

    climate regime

Once all the parameters are set you can run the analysis by clicking on the **Load the indicators** button.
It takes time to calulate all the sub-indicator. There is an area that display the current state of analysis just below the **Load the indicators** button.

.. figure:: https://raw.githubusercontent.com/12rambau/sdg_indicators_module/master/doc/img/process.png

    Process button

Download the result
-------------------

 - The process by default download the zonal statistics in the download folder.
 - To download the results in your local computer, click on the botons available above the map.
 - To download all the Geotif file in the SEPAL folder click on the botton below the map.
 
.. figure:: https://raw.githubusercontent.com/12rambau/sdg_indicators_module/master/doc/img/results.png

    final results

