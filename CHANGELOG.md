## 1.1.1 (2023-10-10)

### Fix

- **reclassify_view**: use sepalwidget card instead
- **geemap**: remove extra display spaces on ui's

### Refactor

- remove unused imports

## 1.1.0 (2023-10-09)

### Feat

- refactor ui entry points
- versioning
- update to sepal_ui@sepal_pre_release
- add pre clacluated landsat ndvi as available sensors
- add MODIS aqua as an available sensor
- add options to select water-body(mask) data
- use the LC custom maps in computation
- specific assetSelect to use UNCCD prepared images
- add a reclassify panel
- add UNCCD classification

### Fix

- update landsat sensors to use collection 2
- update the proper UNCCD land cover classes
- link custom_lc_matrix with the variable
- add functions to preproces modis npp and hide vi and trend widget
- remove int()
- adapt land cover legend to display custom land cover classes.
- check custom land cover inputs
- hormonize landcover output data type
- layout of the productivity assessment period
- remove the appropriate file
- use complex fileprefix #89
- force image in the reclassify tool
- use letters in the transition matrix Fix #85
- force trigger sensors bining
- set default parameters
- specify band
- export the legend as png Fix #69
- add comments to the functions Fix #80
- split computation in folders use parameters to create folders and subfolders Fix #79
- export the graphs as png Fix #77 #79
- use CCI colormap Fix #70
- use colorblind palette for degradation Fix #69
- remove download btn Fix #78
- change the scale according to the sensor Fix #74
- change AOI thickness Fix #67
- apply pre-commit hooks
- add requirements #68
- sensor select compatible with modis Fix #73
- change productivity layer name Fix #65

### Refactor

- remove legacy raise
