from ldms.analysis.gee import GEE
from ldms.enums import RasterSourceEnum
from ldms.utils.common_util import validate_years, return_with_error, cint
import ee
import datetime
from django.utils.translation import gettext as _
from ldms.utils.vector_util import get_vector
import json
from ee.ee_exception import EEException
import logging

log = logging.getLogger(f'ldms.apps.{__name__}')

class ForestFireGEE(GEE):
	"""
	Wrapper for computing forest fire based on GEE
	https://accounts.google.com/o/oauth2/auth/oauthchooseaccount?client_id=517222506229-vsmmajv00ul0bs7p89v5m89qs8eb9359.apps.googleusercontent.com&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fearthengine%20https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdevstorage.full_control&redirect_uri=urn%3Aietf%3Awg%3Aoauth%3A2.0%3Aoob&response_type=code&code_challenge=0f2LkQU__YY5sYKHf8MgQF0T8ZUbTEXIDkXZeGk0ZMg&code_challenge_method=S256&flowName=GeneralOAuthFlow
	
	4/1AfDhmriTlKuyxQpGJipthRXfaJUmMaGQnUU6Pg03VH7NNJAJnOZwrSqiRvA

	See https://code.earthengine.google.com/b455ba8cf4b5bee822bb7ff8935e6209
	See https://un-spider.org/advisory-support/recommended-practices/recommended-practice-burn-severity/burn-severity-earth-engine
	"""
	def __init__(self, **kwargs):
		"""
		Args:
			**admin_level (int)**: 
				The administrative level for the polygon to be used in case a shapefile id has been provided for the parameter **vector**.
			**shapefile_id (int)**: 
				ID of an existing shapefile. 
			**custom_coords (GeoJSON, or GEOSGeometry)**: 
				Coordinates which may be as a result of a custom drawn polygon or a Geometry object in form of GeoJSON.
			**prefire_start (int)**: 
				Pre-fire start date. 
			**prefire_end (int)**: 
				Pre-fire end date. 
			**postfire_start (int)**: 
				Post-fire start date. 
			**postfire_end (int)**: 
				Post-fire start date. 
			**raster_source (string)**: 
				Either Sentinel-2 or Landsat,
			**request**:
				WebRequest 
		"""
		self.admin_level = kwargs.get('admin_level', None)
		self.shapefile_id = kwargs.get('shapefile_id', None)
		self.custom_vector_coords = kwargs.get('custom_vector_coords', None)
		self.admin_0 = kwargs.get('admin_0', None)

		# Set start and end dates of a period BEFORE the fire. Make sure it is long enough for 
		# Sentinel-2 to acquire an image (repitition rate = 5 days). Adjust these parameters, if
		# your ImageCollections (see Console) do not contain any elements.
		self.prefire_start = kwargs.get('prefire_start', None) # '2016-12-20'  
		self.prefire_end = kwargs.get('prefire_end', None) # '2016-12-20'  
		
		# Now set the same parameters for AFTER the fire.
		self.postfire_start = kwargs.get('postfire_start', None) # '2017-02-20'
		self.postfire_end = kwargs.get('postfire_end', None) # '2017-03-28'

		self.platform = kwargs.get('raster_source', RasterSourceEnum.LANDSAT8.value)# "L8"
		self.error = "" 
		self.request = kwargs.get('request', None)

	def calculate_forest_fire(self):
		"""
		Compute forest fire

		See https://colab.research.google.com/github/csaybar/EEwPython/blob/dev/10_Export.ipynb#scrollTo=AlrN7x3LMC7S
		for examples on exporting data from Python

		See https://un-spider.org/advisory-support/recommended-practices/recommended-practice-burn-severity/burn-severity-earth-engine
		See https://code.earthengine.google.com/b455ba8cf4b5bee822bb7ff8935e6209

		Returns a path to GEE where the results can be downloaded
		"""

		def get_statistics():
			"""
			ADD BURNED AREA STATISTICS
			"""

			def area_count(cnr, name):
				"""A function to derive extent of one burn severity class
					arguments are class number and class name
				Args:
					cnr ([type]): [description]
					name ([type]): [description]
				"""
				singleMask = classified.updateMask(classified.eq(cnr))  # mask a single class
				stats = singleMask.reduceRegion(**{
					'reducer': ee.Reducer.count(), # count pixels in a single class
					'geometry': self.area,
					'scale': 30
				})
				pix =  ee.Number(stats.get('sum'))
				hect = pix.multiply(900).divide(10000) # Landsat pixel = 30m x 30m --> 900 sqm
				perc = pix.divide(allpixels).multiply(10000).round().divide(100) # get area percent by class and round to 2 decimals
				
				arealist.append({ 'class': name, 'pixels': pix.getInfo(), 'hectares': hect.getInfo(), 'percentage': perc.getInfo() })

			# Seperate result into 8 burn severity classes
			thresholds = ee.Image([-1000, -251, -101, 99, 269, 439, 659, 2000])
			classified = dNBR.lt(thresholds).reduce('sum').toInt()

			# count number of pixels in entire layer
			allpix = classified.updateMask(classified) # mask the entire layer
			pixstats = allpix.reduceRegion(**{
				'reducer': ee.Reducer.count(),  # count pixels in a single class
				'geometry': self.area,
				'scale': 30
			})
			
			allpixels = ee.Number(pixstats.get('sum')) # extract pixel count as a number

			# create an empty list to store area values in
			arealist = []
			
			# severity classes in different order
			names2 = ['NA', 'High Severity', 'Moderate-high Severity',
					'Moderate-low Severity', 'Low Severity','Unburned',
					 'Enhanced Regrowth, Low', 'Enhanced Regrowth, High']

			# execute function for each class
			for i, clsname in enumerate(names2):			
				area_count(i, clsname)

			print('Burned Area by Severity Class', arealist, '--> click list objects for individual classes')
			return arealist

		# set prefire and postfire as dates
		self.prefire_start = self.parse_date(self.prefire_start)
		self.prefire_end = self.parse_date(self.prefire_end)
		self.postfire_start = self.parse_date(self.postfire_start)
		self.postfire_end = self.parse_date(self.postfire_end)

		sy, ey, period_error = self.validate_periods()
		if period_error:
			return self.return_with_error(period_error)

		# validate vector
		vector, error = self.get_vector()
		if error:
			return self.return_with_error(error)
		
		super(ForestFireGEE, self).initialize()
		self.geometry = ee.Geometry.Polygon(json.loads(vector)['coordinates'][0])
		self.set_platform(self.platform)
		self.filter_rasters()

		# validate that prefire and postfire collections have values
		# Get the number of images.		

		# Apply platform-specific cloud mask
		if str(self.platform.value).lower().strip() == RasterSourceEnum.SENTINEL2.value.lower():
			prefire_CM_ImCol = self.prefireImCol.map(self.maskS2sr)
			postfire_CM_ImCol = self.postfireImCol.map(self.maskS2sr)
		else:
			prefire_CM_ImCol = self.prefireImCol.map(self.maskL8sr)
			postfire_CM_ImCol = self.postfireImCol.map(self.maskL8sr)

		pre_mos = self.prefireImCol.mosaic().clip(self.area)
		post_mos = self.postfireImCol.mosaic().clip(self.area)

		pre_cm_mos = prefire_CM_ImCol.mosaic().clip(self.area)
		post_cm_mos = postfire_CM_ImCol.mosaic().clip(self.area)

		# Add the clipped images to the console on the right
		print("Pre-fire True Color Image: ", pre_mos)
		print("Post-fire True Color Image: ", post_mos)

		if self.platform.value == RasterSourceEnum.SENTINEL2.value:
			preNBR = pre_cm_mos.normalizedDifference(['B8', 'B12'])
			postNBR = post_cm_mos.normalizedDifference(['B8', 'B12'])
		else:
			preNBR = pre_cm_mos.normalizedDifference(['B5', 'B7'])
			postNBR = post_cm_mos.normalizedDifference(['B5', 'B7'])

		# The result is called delta NBR or dNBR
		dNBR_unscaled = preNBR.subtract(postNBR)

		# Scale product to USGS standards
		dNBR = dNBR_unscaled.multiply(1000)

		# Add the difference image to the console on the right
		print("Difference Normalized Burn Ratio: ", dNBR)

		try:
			path = dNBR.getDownloadUrl({
				'scale': 30, 			
				'crs': 'EPSG:4326', 
				'region': self.geometry
			})
			# print (path)
		except EEException as e:
			print(str(e))
			log.log(logging.ERROR, str(e))
			path = ""

		# get statistics
		stats = get_statistics()
		print("Stats: ", stats)
		
		stats_obj = {
			"prefire_start": self.format_date(self.prefire_start),
			"prefire_end": self.format_date(self.prefire_end),
			"postfire_start": self.format_date(self.postfire_start),
			"postfire_start": self.format_date(self.postfire_end),
			"rasterfile": str(path),
			"nodata": None, # nodata_count * (resolution or 1),
			'stats': stats,
		} 
		return stats_obj 

	def format_date(self, dt):
		dtformat = "%Y-%m-%d"
		return dt.strftime(dtformat)

	def parse_date(self, dt_str):
		return datetime.datetime.strptime(dt_str, "%Y-%m-%d")

	def export_image(self, image, description):
		# Export the image, specifying scale and region.
		task = ee.batch.Export.image.toDrive(**{
			'image': image,
			'description': description,
			'folder':'Example_folder',
			'scale': 100,
			# 'region': geometry.getInfo()['coordinates']
		})
		task.start()

		import time 
		while task.active():
			print('Polling for task (id: {}).'.format(task.id))
			time.sleep(5)

	def set_platform(self, platform):
		"""
		SELECT one of the following: 'L8'  or 'S2' 
		"""
		if platform == RasterSourceEnum.SENTINEL2:
			self.ImCol = 'COPERNICUS/S2'
			pl = 'Sentinel-2'
		else:
			self.ImCol = 'LANDSAT/LC08/C01/T1_SR'
			pl = 'Landsat 8'

		# print(ee.String('Data selected for analysis: ').cat(pl))
		# print(ee.String('Fire incident occurred between ').cat(self.prefire_end).cat(' and ').cat(self.postfire_start))

	def filter_rasters(self):
		"""
		Filter rasters in GEE
		"""
		# Location
		self.area = ee.FeatureCollection(self.geometry)
		imagery = ee.ImageCollection(self.ImCol)

		self.prefireImCol = ee.ImageCollection(imagery
			# Filter by dates.
			.filterDate(self.prefire_start, self.prefire_end)
			# Filter by location.
			.filterBounds(self.area))

		self.postfireImCol = ee.ImageCollection(imagery
			# Filter by dates.
			.filterDate(self.postfire_start, self.postfire_end)
			# Filter by location.
			.filterBounds(self.area))

		# Add the clipped images to the console on the right
		print("Pre-fire Image Collection: ", self.prefireImCol)
		print("Post-fire Image Collection: ", self.postfireImCol)

	def maskS2sr(self, image):
		# Bits 10 and 11 are clouds and cirrus, respectively.
		cloudBitMask = ee.Number(2).pow(10).int()
		cirrusBitMask = ee.Number(2).pow(11).int()
		# Get the pixel QA band.
		qa = image.select('QA60')
		# All flags should be set to zero, indicating clear conditions.
		mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))
		# Return the masked image, scaled to TOA reflectance, without the QA bands.
		return image.updateMask(mask).copyProperties(image, ["system:time_start"])

	def maskL8sr(self, image):
		# Bits 3 and 5 are cloud shadow and cloud, respectively.
		cloudShadowBitMask = 1 << 3
		cloudsBitMask = 1 << 5
		snowBitMask = 1 << 4
		# Get the pixel QA band.
		qa = image.select('pixel_qa')
		# All flags should be set to zero, indicating clear conditions.
		mask = qa.bitwiseAnd(cloudShadowBitMask).eq(0).And(qa.bitwiseAnd(cloudsBitMask).eq(0)).And(qa.bitwiseAnd(snowBitMask).eq(0))
		# Return the masked image, scaled to TOA reflectance, without the QA bands.
		return image.updateMask(mask).select("B[0-9]*").copyProperties(image, ["system:time_start"])

	def validate_periods(self):
		"""
		Validate the start and end periods

		Returns:
			tuple (Start_Year, End_Year)
		"""		
		# validate pre-fire
		start_year = self.prefire_start.year
		end_year = self.prefire_end.year
		start_year, end_year, error = validate_years(
						start_year=start_year,
						end_year=end_year,
						both_valid=True)
		if error:
			error = _("Invalid Pre-fire dates. The start year must be earlier than end year")
			return (start_year, end_year, error)
		
		# validate post-fire
		start_year = self.postfire_start.year
		end_year = self.postfire_end.year
		start_year, end_year, error = validate_years(
						start_year=start_year,
						end_year=end_year,
						both_valid=True)
		if error:
			error = _("Invalid Post-fire dates. The start year must be earlier than end year")
			return (start_year, end_year, error)

		# check that the period-ranges are not the same
		if self.prefire_start == self.postfire_start:
			error = _("Invalid start dates. The start date for pre-fire period must be different from post-fire start year")
			return (start_year, end_year, error)
		if self.prefire_end == self.postfire_end:
			error = _("Invalid end dates. The end date for pre-fire period must be different from post-fire end year")
			return (start_year, end_year, error)
		# check that pre-fire is earlier than post-fire
		if self.prefire_start >= self.postfire_start:
			error = _("Invalid date ranges. The start date for pre-fire period must be earlier than post-fire start year")
			return (start_year, end_year, error)

		return (start_year, end_year, error)

	def get_vector(self):
		return get_vector(admin_level=self.admin_level, 
						  shapefile_id=self.shapefile_id, 
						  custom_vector_coords=self.custom_vector_coords, 
						  admin_0=self.admin_0,
						  request=self.request)

	def return_with_error(self, error):		
		self.error = error
		return return_with_error(self.request, error)