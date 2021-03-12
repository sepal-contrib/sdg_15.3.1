# 1. Select an AOI
In this first step you need to select a AOI using one of the provided methods. You can choose between four methods.

![select_aoi](./img/select_aoi.png) 

## 1.1 Country boundaries
Once you reach the `country boundaries` value in the dropdown and select it, a new dropdown appears. 

![aoi dropdown](./img/aoi_dropdown.png)

There you can select a country name in the list provided. They correspond to every available country in the LSIB-2017 list. 

After validating your country, the map will zoom on the country you've validated and will create an aoi_[country_code] asset on your GEE account. It will be available for other projects.

> :warning: The output can select the wrong country, before validating your selection please verify in the blue alert that the `selected country` is the one you want to use. If wrong try to select it again.

![country boundaries](./img/country_boundaries.png) 

## 1.2 Draw a shape

Once you have selected `draw a shape` in the dropdown, two new input will appear: 
 - Select a filename
 - The drawing tool on the map
 
 The filename will be the name of your AOI. It sets an auto-generated value by default. If you want to change it you can write anything in alphanumeric characters
 
 The drawing tool on the map allows you to draw shapes (rectangles, polygons and circle) 
 
 > :warning: Multiple geometries could lead to various bug or crash. If needed please consider running your analysis in two steps
 
After validating your shape, the map will zoom on the AOI you've validated and will create an aoi_[filename] asset on your GEE account. It will be available for other projects.

![draw a shape](./img/draw_shape.png)

## 1.3 Import shapefile
Importing your own shapefile in this module will be perform in two steps. 
First you need to import the shape to your sepal folder and then use it. 

In a new application tab (1), select 'jupyter notebook' (2).
![applications](./img/applications.png)

You should obtain a description of your local folder in Sepal (3). click on `upload` (4) and select the required files.

![jupyter](./img/jupyter.png)
 

> :warning: in order to perform the construction of your AOI, the module will require you to upload .shp, .dbf and .shx with the same name in the same folder

> :question: It is strongly advised to put all your shapefile in a new folder such as `degradaion_input`
 
It will show you a complete list of the full (with all the required .db, .shx, .shp ...) available shapefile in your sepal env.
![folder_struct](./img/filepath.png)
![shapefile_import](./img/shapefile.png)

After validating your shape, the map will zoom on the AOI you've have validated and will create an aoi_[filename] asset on your GEE account. It will be available for other projects.

## 1.4 import GEE asset

Once you have selected `use GEE asset` in the dropdown, just enter the name (2) of your asset as it appears on your GEE account (1) 

![custom asset](./img/GEE_assets.png)


After validating your AOI the map will zoom on the AOI you have validated

---
[ go to  &rarr; 2. Calculate indicator 15.3.1](./calculate_15_3_1.md) 

[return &larr; to table of content](./doc.md)



