from functools import partial
import ee

# import json

from component import parameter as pm

ee.Initialize()


def productivity_trajectory(
    model, integrated_annual_vi, climate_yearly_integration, output
):
    """
        Productivity Trend describes the trajectory of change in productivity over time. Trend is calculated by
        fitting a robust, non-parametric linear regression model.
        The significance of trajectory slopes at the P <= 0.05 level should be reported in terms of three classes:
            1) Z score < -1.96 = Potential degradation, as indicated by a significant decreasing trend,
            2) Z score > 1.96 = Potential improvement, as indicated by a significant increasing trend, or
            3) Z score > -1.96 AND < 1.96 = No significant change

    In order to correct the effects of climate on productivity, climate adjusted trend analysis can be performed.
    There such methods are coded for the trajectory analysis.

    The following code runs the selected trend method and produce an output by reclassifying the trajectory slopes.
    """

    # Run the selected algorithm
    trajectories = [traj["value"] for traj in pm.trajectories]

    # ndvi trend
    if model.trajectory == trajectories[0]:
        z_score = vi_trend(model.start, model.end, integrated_annual_vi)
    # residual trend analysis
    elif model.trajectory == trajectories[1]:
        z_score = restrend(
            model.start, model.end, integrated_annual_vi, climate_yearly_integration
        )
    # Water use efficiency
    elif model.trajectory == trajectories[2]:
        # TODO:
        raise NameError("this method is under development")
    # rain use efficiency trend
    elif model.trajectory == trajectories[3]:
        z_score = rain_use_efficiency_trend(
            model.start, model.end, integrated_annual_vi, climate_yearly_integration
        )

    # Define Kendall parameter values for a significance of 0.05
    five_levels_trajectory = (
        ee.Image(0)
        .where(z_score.lt(-1.96), 1)
        .where(z_score.lt(-1.28).And(z_score.gte(-1.96)), 2)
        .where(z_score.gte(-1.28).And(z_score.lte(1.28)), 3)
        .where(z_score.gt(1.28).And(z_score.lte(1.96)), 4)
        .where(z_score.gt(1.96), 5)
        .rename("trajectory_5_levels")
        .uint8()
    )

    trajectory = (
        ee.Image(0)
        .where(z_score.lt(-1.96), 1)
        .where(z_score.gte(-1.96), 2)
        .rename("trajectory")
        .uint8()
    )

    return five_levels_trajectory.addBands(trajectory)


def productivity_performance(
    aoi_model, model, nvdi_yearly_integration, climate_yearly_integration, output
):
    """
    It measures local productivity relative to other similar vegetation types in similar land cover types and bioclimatic regions. It indicates
    how a region is performing relative to other regions with similar productivity potential.
        Steps:
        * Computation of mean NDVI for the analysis period,
        * Creation of ecologically similar regions based on USDA taxonomy and ESA CCI land cover data sets.
        * Extraction of mean NDVI for each region, creation of  a frequency distribution of this data to determine the value that represents 90th percentile,
        * Computation of the ratio of mean NDVI and max productivity (90th percentile)

    """

    # land cover data from esa cci
    if model.lceu == "calculate":
        landcover = ee.ImageCollection(pm.land_cover_ic)

        soil_taxonomy = (
            ee.Image(pm.soil_taxonomy)
            .select("b0")
            .clip(aoi_model.feature_collection.geometry().bounds())
        )

        # should not be here it's a hidden parameter

        # Handle case of year_start that isn't included in the CCI data
        lc_year_start = min(
            max(model.start, pm.land_cover_first_year), pm.land_cover_max_year
        )

        #################

        # reclassify lc to ipcc classes
        lc_reclass = (
            landcover.filter(
                ee.Filter.calendarRange(lc_year_start, lc_year_start, "year")
            )
            .first()
            .remap(pm.ESA_lc_classes, pm.reclassification_matrix)
        )

        lc_eco_functional_unit = soil_taxonomy.multiply(100).add(lc_reclass)
    elif model.lceu == "wte":
        lc_eco_functional_unit = ee.Image(pm.wte).clip(
            aoi_model.feature_collection.geometry().bounds()
        )
    # TODO: add all the available LCEU datasets

    # compute mean ndvi for the period
    ndvi_mean = (
        nvdi_yearly_integration.select("vi").reduce(ee.Reducer.mean()).rename(["vi"])
    )

    ################

    # create a binary mask.
    mask = ndvi_mean.neq(0)

    # create a 2 band raster to compute 90th percentile per ecoregion (analysis restricted by mask and study area)
    ndvi_id = ndvi_mean.addBands(lc_eco_functional_unit).updateMask(mask)

    # compute 90th percentile by unit
    percentile_90 = ndvi_id.reduceRegion(
        reducer=ee.Reducer.percentile([90]).group(groupField=1, groupName="code"),
        geometry=aoi_model.feature_collection.geometry(),
        scale=30,
        maxPixels=1e15,
    )

    # Extract the cluster IDs and the 90th percentile
    groups = ee.List(percentile_90.get("groups"))
    ids = groups.map(lambda d: ee.Dictionary(d).get("code"))
    percentile = groups.map(lambda d: ee.Dictionary(d).get("p90"))

    # remap the similar ecoregion raster using their 90th percentile value
    ecoregion_perc90 = lc_eco_functional_unit.remap(ids, percentile)

    # compute the ratio of observed ndvi to 90th for that class
    observed_ratio = ndvi_mean.divide(ecoregion_perc90)

    # create final degradation output layer (0 is background), 2 is not
    # degreaded, 1 is degraded
    performance = (
        ee.Image(0)
        .where(observed_ratio.gte(0.5), 2)
        .where(observed_ratio.lte(0.5), 1)
        .rename("performance")
        .uint8()
    )

    return performance


def productivity_state(aoi_model, model, integrated_annual_vi, output):
    """
    It represents the level of relative productivity in a pixel compred to a historical observations of productivity for that pixel.
    For more, see Ivits, E., & Cherlet, M. (2016). Land productivity dynamics: towards integrated assessment of land degradation at
    global scales. In. Luxembourg: Joint Research Centr, https://publications.jrc.ec.europa.eu/repository/bitstream/JRC80541/lb-na-26052-en-n%20.pdf
    It alows for the detection of recent changes in primary productivity as compared to the baseline period.

    Methodology:
    Mean annual NPP is compared to the mean NPP of most recent three years.
    $$\mu =\frac{\sum_{y-15}^{y-3}x_y}{13} $$
        $$\sigma = \sqrt{\frac{\sum_{y-15}^{y-3}\left(x_y -\mu \right)^2}{13}}$$
        $$\bar{x} =\frac{\sum_{y-2}^{y}x_y}{3}$$
        $$z=\frac{\bar{x}-\mu}{\frac{\sigma}{\sqrt{3}}}$$

        Where, x= productivity metric (annual vegetation index), y i the year of analysis,
    """

    # Filter the annual data of three most recent years
    recent_yaers_filter = ee.Filter.rangeContains("year", model.end - 2, model.end)
    previous_year_filter = ee.Filter.rangeContains("year", model.start, model.end - 2)

    # compute mean ndvi for the baseline and target period period
    recent_vi_xbar = (
        integrated_annual_vi.filter(recent_yaers_filter)
        .select("vi")
        .reduce(ee.Reducer.mean())
        .rename(["vi"])
    )

    previous_vi_mu = (
        integrated_annual_vi.filter(previous_year_filter)
        .select("vi")
        .reduce(ee.Reducer.mean())
        .rename(["vi"])
    )

    previous_vi_sigma = (
        integrated_annual_vi.filter(previous_year_filter)
        .select("vi")
        .reduce(ee.Reducer.stdDev())
        .rename(["vi"])
    )
    z_score = recent_vi_xbar.subtract(previous_vi_mu).divide(
        previous_vi_sigma.divide(ee.Number(3).sqrt())
    )

    # {0:"nodata", 1: "Degraded", 2: "At risk of degrading", 3: "No significant chnage", 4:"Potentially improving", 5:"Improving"}
    five_levels_state = (
        ee.Image(0)
        .where(z_score.lt(-1.96), 1)
        .where(z_score.lt(-1.28).And(z_score.gte(-1.96)), 2)
        .where(z_score.gte(-1.28).And(z_score.lte(1.28)), 3)
        .where(z_score.gt(1.28).And(z_score.lte(1.96)), 4)
        .where(z_score.gt(1.96), 5)
        .rename("state_5_levels")
        .uint8()
    )

    # {0:"Nodata", 1:"Degraded", 2:"Not Degraded"}
    state = (
        ee.Image(0)
        .where(z_score.lt(-1.96), 1)
        .where(z_score.gte(-1.96), 2)
        .rename("state")
        .uint8()
    )

    return five_levels_state.addBands(state)


def productivity_final(trajectory, performance, state, output):
    trajectory_class = trajectory.select("trajectory")
    performance_class = performance.select("performance")
    state_class = state.select("state")

    productivity = (
        ee.Image(0)
        .where(
            trajectory_class.eq(1).And(state_class.eq(1)).And(performance_class.eq(1)),
            1,
        )
        .where(
            trajectory_class.eq(1).And(state_class.eq(1)).And(performance_class.eq(2)),
            1,
        )
        .where(
            trajectory_class.eq(1).And(state_class.eq(2)).And(performance_class.eq(1)),
            1,
        )
        .where(
            trajectory_class.eq(1).And(state_class.eq(2)).And(performance_class.eq(2)),
            2,
        )
        .where(
            trajectory_class.eq(2).And(state_class.eq(1)).And(performance_class.eq(1)),
            1,
        )
        .where(
            trajectory_class.eq(2).And(state_class.eq(1)).And(performance_class.eq(2)),
            2,
        )
        .where(
            trajectory_class.eq(2).And(state_class.eq(2)).And(performance_class.eq(1)),
            1,
        )
        .where(
            trajectory_class.eq(2).And(state_class.eq(2)).And(performance_class.eq(2)),
            2,
        )
        .rename("productivity")
    )

    return productivity.uint8()


def productivity_final_GPG1(trajectory, performance, state, output):
    trajectory_class = trajectory.select("trajectory")
    performance_class = performance.select("performance")
    state_class = state.select("state")

    productivity = (
        ee.Image(0)
        .where(
            trajectory_class.eq(1).And(state_class.eq(1)).And(performance_class.eq(1)),
            1,
        )
        .where(
            trajectory_class.eq(1).And(state_class.eq(1)).And(performance_class.eq(2)),
            1,
        )
        .where(
            trajectory_class.eq(1).And(state_class.eq(2)).And(performance_class.eq(1)),
            1,
        )
        .where(
            trajectory_class.eq(1).And(state_class.eq(2)).And(performance_class.eq(2)),
            1,
        )
        .where(
            trajectory_class.eq(2).And(state_class.eq(1)).And(performance_class.eq(1)),
            1,
        )
        .where(
            trajectory_class.eq(2).And(state_class.eq(1)).And(performance_class.eq(2)),
            2,
        )
        .where(
            trajectory_class.eq(2).And(state_class.eq(2)).And(performance_class.eq(1)),
            2,
        )
        .where(
            trajectory_class.eq(2).And(state_class.eq(2)).And(performance_class.eq(2)),
            2,
        )
        .rename("productivity")
    )

    return productivity.uint8()


def vi_trend(start, end, integrated_annual_vi):
    """Calculate VI trend.

    Calculates the trend of temporal VI using VI data from selected satellite dataset.
    Areas where changes are not significant
    are masked out using a Mann-Kendall tau.
    """

    # Compute Kendall statistics
    n = end - start + 1
    z_coefficient = pm.z_coefficient(n)
    kendall_trend = (
        integrated_annual_vi.select("vi")
        .reduce(ee.Reducer.kendallsCorrelation(), 2)
        .select("vi_tau")
        .multiply(z_coefficient)
    )

    return kendall_trend


def restrend(start, end, ndvi_yearly_integration, climate_yearly_integration):
    """
      Residual trend analysis(RESTREND) predicts NDVI based on the given rainfall.
      It uses linear regression model to predict NDVI for a given rainfall amount.
      The residual (Predicted - Obsedved) NDVI trend is considered as productivity
      change that is indipendent of climatic variation.
      For further details, check the reference: Wessels, K.J.; van den Bergh, F.;
      Scholes, R.J. Limits to detectability of land degradation by trend analysis of
      vegetation index data. Remote Sens. Environ. 2012, 125, 10–22.
     Inputs:
      start: Start of the historical period
      end: End of the monitoring period
      ndvi_yearly_integration: ee.ImageCollection of annul NDVI series
      climate_yearly_integration: ee.ImageCollection of annul rainfall series
    Output: A tuple of two ee.Image, linear trend and Mann-Kendall trend
    """

    # Apply function to create image collection of ndvi and climate
    ndvi_climate_yearly_integration = ndvi_climate_merge(
        climate_yearly_integration, ndvi_yearly_integration, start, end
    )

    # Compute linear trend function to predict ndvi based on climate (independent are followed by dependent var
    linear_model_climate_ndvi = ndvi_climate_yearly_integration.select(
        ["clim", "vi"]
    ).reduce(ee.Reducer.linearFit())

    def ndvi_prediction_climate(image, list):
        """predict NDVI from climate. part of p_restrend function"""

        ndvi = (
            linear_model_climate_ndvi.select("offset")
            .add(
                linear_model_climate_ndvi.select("scale").multiply(image.select("clim"))
            )
            .set({"year": image.get("year")})
        )

        return ee.List(list).add(ndvi)

    # Apply function to  predict NDVI based on climate
    first = ee.List([])
    predicted_yearly_ndvi = ee.ImageCollection(
        ee.List(
            ndvi_climate_yearly_integration.select("clim").iterate(
                ndvi_prediction_climate, first
            )
        )
    )

    # Apply function to compute NDVI annual residuals
    # residual_yearly_ndvi = image_collection_residuals(start, end, nvdi_yearly_integration, predicted_yearly_ndvi)
    residual_yearly_ndvi = ndvi_yearly_integration.map(
        partial(ndvi_residuals, modeled=predicted_yearly_ndvi)
    )

    # Compute Kendall statistics
    n = end - start + 1
    z_coefficient = pm.z_coefficient(n)
    kendall_trend = (
        residual_yearly_ndvi.select("vi_res")
        .reduce(ee.Reducer.kendallsCorrelation(), 2)
        .select("vi_res_tau")
        .multiply(z_coefficient)
    )

    return kendall_trend


def rain_use_efficiency_trend(
    start, end, ndvi_yearly_integration, climate_yearly_integration
):
    """
    Calculate trend based on rain use efficiency.
    It is the ratio of ANPP(annual integral of NDVI as proxy) to annual precipitation.
    """

    # Apply function to create image collection of ndvi and climate
    ndvi_climate_yearly_integration = ndvi_climate_merge(
        climate_yearly_integration, ndvi_yearly_integration
    )

    # Apply function to compute ue and store as a collection
    ue_yearly_collection = ndvi_climate_yearly_integration.map(use_efficiency_ratio)

    # Compute Kendall statistics
    n = end - start + 1
    z_coefficient = pm.z_coefficient(n)
    kendall_trend = (
        ue_yearly_collection.select("ue")
        .reduce(ee.Reducer.kendallsCorrelation(), 2)
        .select("ue_tau")
        .multiply(z_coefficient)
    )

    return kendall_trend


def ndvi_climate_merge(
    climate_yearly_integration, ndvi_yearly_integration, start=None, end=None
):
    """Creat an ImageCollection of annual integral of NDVI and annual inegral of climate data"""

    # create the filter to use in the join
    join_filter = ee.Filter.equals(leftField="year", rightField="year")

    join = ee.Join.inner("clim", "vi", "year")

    # join the 2 collections
    inner_join = join.apply(
        climate_yearly_integration.select("clim"),
        ndvi_yearly_integration.select("vi"),
        join_filter,
    )

    joined = inner_join.map(
        lambda feature: ee.Image.cat(feature.get("clim"), feature.get("vi")).set(
            "year", ee.Image(feature.get("clim")).get("year")
        )  # both have the same year
    )

    return ee.ImageCollection(joined)


def ndvi_residuals(image, modeled):
    """Function to compute residuals (ndvi obs - ndvi pred). part of p_restrend function"""

    # get the year from image props
    year = image.get("year")

    ndvi_o = image.select("vi")

    ndvi_p = modeled.filter(ee.Filter.eq("year", year)).first()

    ndvi_r = (
        ee.Image.constant(year)
        .float()
        .addBands(ndvi_o.subtract(ndvi_p))
        .rename(["year", "vi_res"])
    )

    return ndvi_r


def use_efficiency_ratio(image):
    """Function to map over the ndvi and climate collection to get the rain use efficiency and store it as an imageCollection"""

    # extract climate and ndvi median values
    ndvi_img = image.select("vi")
    clim_img = image.select("clim").divide(1000)
    year = image.get("year")
    divide_img = (
        ndvi_img.divide(clim_img)
        .addBands(ee.Image.constant(year).float())
        .rename(["ue", "year"])
        .set({"year": year})
    )

    return divide_img
