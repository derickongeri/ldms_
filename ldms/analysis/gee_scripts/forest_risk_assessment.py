import ee
import json

ROI = None # ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017')
START_DATE = '2021-08-01'
END_DATE = '2021-08-30'
COUNTRY_NAME = "Algeria"
COUNTRY_VECTOR = None
IN_COLAB_CONTEXT = False
SCALE = 200

def entrypoint(aoi, country_name, analysis_start, analysis_end, scale):
	"""Entry point for this script. variables will be overridden at this point

	Due to GEE limitations, we will restrict computation at country level
	Args:
		aoi (geojson): Area of interest. This will be country coords
		country_name (string): Name of country whose alerts you want to compute
		analysis_start (string): Analysis period start date string of the format 'YYYY-mm-dd'
		analysis_end (string): Analysis period end date string of the format 'YYYY-mm-dd'
		scale (int): Scale to use when generating alerts
	"""

	global START_DATE, END_DATE, COUNTRY_NAME, COUNTRY_VECTOR, ROI, SCALE
	# geometry = ee.Geometry.Polygon(coords[0])

	#ee.Geometry.Polygon(json.loads(vector)['coordinates'][0])
	# geom = ee.Geometry.Polygon(json.loads(aoi)['coordinates'][0])
	#geometry = ee.Geometry.Polygon([[[3.112174255057627, 36.73874167162853],[3.112174255057627, 36.19094855897513],[5.067740661307627, 36.19094855897513],[5.067740661307627, 36.73874167162853]]])
	COUNTRY_VECTOR = aoi
	START_DATE = analysis_start 
	END_DATE = analysis_end
	COUNTRY_NAME = country_name
	ROI = ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017')
	SCALE = scale

def _get_alerts(country_name):
	"""Compute forest fire risk alerts

	Args:
		country_name (string): Country of computation

	Returns:
		[obj, list[], []]: Returns a tuple of [merged_tiff_url, list_of_individual_daily_tiff, daily_stats]
	"""
	# Load country boundary form International Boundary dataset.
	country = filter_region(country_name)

	# Elevation data - Posibility fo spread
	dem_dataset = ee.Image('USGS/SRTMGL1_003').select('elevation').clip(country)

	# Land surface temperature MOD11A2
	datasetMOD11A2 = ee.ImageCollection('MODIS/006/MOD11A2') \
					.filter(ee.Filter.date(START_DATE, END_DATE))
	modisLST = datasetMOD11A2.select(['LST_Day_1km'],['ST']).mean().clip(country)

	# Map.addLayer(modisLST, landSurfaceTemperatureVis,'Land Surface Temperature')

	# Land Cover Urban class - Anthropogenic Influence
	# LC_dataset = ee.Image("COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019").select('urban-coverfraction')
	# Map.addLayer(LC_dataset.gte(10).clip(country), {}, "Land Cover")

	# Start with an image collection for a 1 month period.
	# and mask out areas that were not observed.
	collection_MODIS = ee.ImageCollection('MODIS/006/MOD09GA') \
			.filterDate(START_DATE, END_DATE) \
			.map(maskEmptyPixels)

	# Map the cloud masking function over the collection.
	collectionCloudMasked = collection_MODIS.map(maskClouds)
	modis_image = collectionCloudMasked.mean().clip(country)

	computedIndices = indexComputations(modis_image)
	image_MNDFI = computedIndices[0] # Modified Normalized Diference Fire Index
	image_PMI = computedIndices[1] # Perpendicular Moisture Index
	image_NDMI = computedIndices[2] # Normalized Multiband Drought index
	pst = pst_caclulation(modisLST, dem_dataset) # Potential Surface Tempe

	if IN_COLAB_CONTEXT:
		# FIRMS DATA- Posibility of ignition
		dataset = ee.ImageCollection('FIRMS') \
			.filter(ee.Filter.date(START_DATE, END_DATE)) \
			.filter(ee.Filter.bounds(country))
	else:
		# FIRMS DATA- Posibility of ignition
		dataset = ee.ImageCollection('FIRMS') \
			.filter(ee.Filter.date(START_DATE, END_DATE)) \
			.filter(ee.Filter.geometry(country)) #python API has no ee.Filter.bounds 

	fires = dataset.select('T21')

	latLong = fires.map(func_sth)

	# print(latLong.getInfo())

	fire_mosaic = latLong.mosaic()
	merged_url = download_image(fire_mosaic)	
	print(merged_url)
	
	# Map.addLayer(latLong, {}, 'Alerts')
	# Map
	# urls = download_collection(latLong)
	# dailystats = [{'day': '2021-08-01', 'count': 115}, {'day': '2021-08-02', 'count': 122}] 
	dailystats = date_pixel_count(latLong)
	return merged_url, [], dailystats

# A function to mask out pixels that did not have observations.
def maskEmptyPixels (image):
	# Find pixels that had observations.
	withObs = image.select('num_observations_1km').gt(0)
	return image.updateMask(withObs)

# A function to mask out cloudy pixels.
def maskClouds (image):
	# Select the QA band.
	QA = image.select('state_1km')
	# Make a mask to get bit 10, the internal_cloud_algorithm_flag bit.
	bitMask = 1 << 10
	# Return an image masking out cloudy areas.
	return image.updateMask(QA.bitwiseAnd(bitMask).eq(0))

# Potential Surface temperature
def pst_caclulation(Image,DEM):
	Po = 101.3 # The Standard atm. pressure at mean sea level
	L = 0.0065 # Temperature lapse rate
	R = 8.31447 # Gas constant
	M = 0.0289644 # Molar mass of dry air
	g = 9.80655 # Earth-surface gravitational acceleration
	To = 20     # Sea level standard temperature
	Z = DEM.select('elevation') #  Elevation

	gm =  g*M
	RL = R*L
	gm_rl = gm*RL

	LZ = DEM.expression('L*Z', {
	'L':L,
	'Z':Z
	}).rename('LZ')

	p = DEM.expression('Po*(1-((LZ/To)**gm_rl))',{

	'Po':Po,
	'LZ': LZ,
	'To': To,
	'gm_rl':gm_rl

	}).rename('p')

	Cp = 1004
	RCP = 287/Cp

	pst = Image.expression('Ts*((Po/p)**RCP)',{
	'p': p.select('p'),
	'Po': Po,
	'Ts':Image.select('ST'),
	'R': R,
	'RCP': RCP

	}).rename('PST')

	return pst

def indexComputations (Image):
	# Modified Normalized Difference Fire index

	mndfi =  Image.expression('((B7-B2)-0.05)/((B7+B2)+0.05)',{'B7':Image.select('sur_refl_b07'),'B2':Image.select('sur_refl_b02')}).rename('MNDFI')

	# Perpendicular Moisture Index
	pmi =  Image.expression('-0.73*((B5-0.94)*(B2-0.028))',{'B5':Image.select('sur_refl_b05'),'B2':Image.select('sur_refl_b02')}).rename('PMI')

	# Normalized Multiband Drought index
	nmdi =  Image.expression('(B2-(B6-B7))/(B2+(B6-B7))',{'B6':Image.select('sur_refl_b06'),'B7':Image.select('sur_refl_b07'),'B2':Image.select('sur_refl_b02')}).rename('NMDI')

	indices = [mndfi,pmi, nmdi]

	return indices

#ADDING LOGN AND LAT TO THE IMAGE
def func_sth(img):
	proj = img.select([0]).projection()
	latlon = ee.Image.pixelLonLat().reproject(proj)
	coords = latlon.select(['longitude', 'latitude']).reduceRegion(ee.Reducer.mean(), 
			get_country(), # geometry, 
			maxPixels=1e19, 
			scale=SCALE)
	lat = ee.List(coords.get('latitude'))
	lon = ee.List(coords.get('longitude'))
	return img.set('latitude', ee.Number(lat),'longitude', ee.Number(lon)).toInt()

# def alert_url_generator(country_name, activity):
# 	"""
# 	If you need a url at regional level, pass country_name=ALL_COUNTRIES
# 	"""
# 	country_alert = _get_alerts(country_name)  
# 	country_url = get_url(alert=country_alert[0] if activity.title()=="Loss" else country_alert[1],
# 												 file_name=generate_file_name(country_name, activity),
# 												 vector=country.geometry())
# 	return country_url

def generate_file_name(country_name, activity):
	return "%s_to_%s_%s_%s.tif" % (START_DATE, END_DATE,
									country_name, "forest_risk")

def is_image_valid(image):
	return len(image.getInfo()['bands']) > 0

def download_collection(images):
	"""
	Download image collection
	"""
	data = images.toList(images.size())
	urls = []
	for i in range(images.size().getInfo()): #This is the number of images in the images collection
		image = ee.Image(data.get(i))
		path = download_image(image)
		urls.append(path)
	return urls

def download_image(img):
	"""
	Download an image
	"""
	if is_image_valid(img):
		url = img.getDownloadUrl({
			'scale': SCALE,
			'crs': 'EPSG:4326',
			'region': get_country()
		})
		# print(url)
		return url
	return None

# def download_image(alert, file_name, vector):
# 	"""
# 	Will export a tif and return the url
# 	"""
# 	if is_image_valid(alert):
# 		# url = downloader(alert, vector)	
# 		url = alert.getDownloadUrl({
# 					'scale': SCALE, 			
# 					'crs': 'EPSG:4326', 
# 					'region': vector.geometry() if IN_COLAB_CONTEXT else vector # ee.Geometry(vector)
# 				})  
# 		return url
# 	return ""

def filter_region(country_name):
	"""Filter regional vector by country"""
	if IN_COLAB_CONTEXT:
		return ROI.filter(ee.Filter.eq('country_na', country_name.upper()))
	else:
		return COUNTRY_VECTOR

def get_country():
	return COUNTRY_VECTOR.geometry() if IN_COLAB_CONTEXT else COUNTRY_VECTOR 

def date_pixel_count(images):
	data = images.toList(images.size())	
	stats = []
	for i in range(images.size().getInfo()): 
		img = ee.Image(data.get(i))
		day =  ee.Date(img.get('system:time_start')).format('YYYY-MM-dd')
		count = img.reduceRegion(ee.Reducer.count(), get_country(), scale=SCALE)
		daily = dict()
		daily['day'] = day.getInfo()
		daily['count'] = count.getInfo()['T21']
		stats.append(daily)
	return stats

def get_results():
	"""This is the main function to be called aside from entry_point.
	Will return the results of the computation

	Returns:
		list: List of tuples of the form (alert, loss_url, gain_url)
	"""
	# Get alerts for the countries of interest
	country_alerts = []
	for i, cntry in enumerate([COUNTRY_NAME]): 
		country_alerts.append(_get_alerts(cntry))# Appends a tuple of ((loss, gain), loss_url, gain_url)

	# print ("Urls: ", [list(x)[1:] for x in country_alerts])
	return country_alerts