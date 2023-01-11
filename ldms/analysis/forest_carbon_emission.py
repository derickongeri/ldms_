
from django.utils.translation import gettext as _
from numpy.core.defchararray import count
from ldms.analysis.lulc import LULC
from ldms.enums import RasterSourceEnum
import ee
from ldms.utils.vector_util import get_vector
from ldms.utils.raster_util import RasterCalcHelper
from ldms.utils.common_util import cint, return_with_error, validate_years
from ldms.utils.raster_util import (
								clip_raster_to_vector, clip_raster_to_vector_windowed,
								return_raster_with_stats, get_raster_models)
from ldms.utils.file_util import (get_media_dir, file_exists)
from ldms.enums import (RasterSourceEnum, RasterCategoryEnum, 
						ForestCoverLossQuinaryEnum, ForestChangeTernaryEnum,
						ForestChangeQuinaryEnum)
from django.conf import settings
import numpy as np
import pandas as pd
import rasterio

class ForestCarbonEmissionSettings:
	SUB_DIR = "" # "forestloss" # Subdirectory to store rasters for carbon emissions
	RASTER_BASE_YEAR = 2000
	MFU_SIZE = 3 # No of pixels squared to determine the minimum forest unit
	MFU_TREE_COVER_THRESHOLD = 30 # Tree cover Percentage within a MFU 
	MFU_NODATA = 0 #Value associated with nodata value
	CARBON_STOCK = 534 # default value of carbon stock in mg
	CO2_FACTOR = 0.2727
	DEGRADATION_EMISSION_PROPORTION = 30 # proportion of carbon emitted by degradation
	EXCLUDE_NOT_A_FOREST = True #If true, MFUs classified as NOT_A_FOREST are to be classified as NODATA
	NODATA = 0 # Value of NODATA as specified in the input maps

class ForestCarbonEmission:
	"""
	Wrapper class for calculating Forest Carbon Emission
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
			**start_year (int)**: 
				Starting year for which raster files should be used. 
			**end_year (int)**: 
				End year for which raster files should be used. 
			**transform (string)**:
				Either of:
					- "area"
					- a string with placeholder e.g x * x to mean square of that value
			**request (Request)**: 
				A Web request object
		""" 
		self.admin_level = kwargs.get('admin_level', None)
		self.shapefile_id = kwargs.get('shapefile_id', None)
		self.custom_vector_coords = kwargs.get('custom_vector_coords', None)
		self.raster_type = kwargs.get('raster_type', None)
		self.start_year = kwargs.get('start_year', None)
		self.end_year = kwargs.get('end_year', None)
		self.analysis_year = kwargs.get('end_year', None)
		self.transform = kwargs.get('transform', "area")
		self.request = kwargs.get('request', None)
		self.error = None
		self.raster_source = kwargs.get('raster_source') or RasterSourceEnum.LULC
		self.enforce_single_year = True
		self.admin_0 = kwargs.get('admin_0', None)
		self.mfu = kwargs.get('mfu') or ForestCarbonEmissionSettings.MFU_SIZE # the no of pixels to make Mimimum Forest Unit (MFU)
		self.mfu_forest_threshold = kwargs.get('mfu_forest_threshold') or ForestCarbonEmissionSettings.MFU_TREE_COVER_THRESHOLD
		self.carbon_stock = kwargs.get('carbon_stock') or ForestCarbonEmissionSettings.CARBON_STOCK
		self.degradation_emission_proportion  = kwargs.get('degradation_emission_proportion') or ForestCarbonEmissionSettings.DEGRADATION_EMISSION_PROPORTION

	def return_with_error(self, error):		
		self.error = error
		return return_with_error(self.request, error)
	
	def validate_periods(self):
		"""
		Validate the start and end periods

		Returns:
			tuple (Start_Year, End_Year)
		"""		
		if self.enforce_single_year:
			self.start_year = self.end_year
		start_year = self.start_year
		end_year = self.end_year

		return validate_years(
							start_year=start_year,
							end_year=end_year,
							both_valid=self.enforce_single_year==0)

	def get_vector(self):
		return get_vector(admin_level=self.admin_level, 
						  shapefile_id=self.shapefile_id, 
						  custom_vector_coords=self.custom_vector_coords, 
						  admin_0=None,
						  request=self.request
						)

	def calculate_carbon_emission(self):
		#return self._calculate_carbon_emission_with_ready_activity_map()
		return self._calculate_carbon_emission_without_activity_map()

	def _calculate_carbon_emission_without_activity_map(self):
		"""
		Compute Forest Carbon Emission
		
		Returns:
			[Response]: [A JSON string with statistic values]
		
		See https://gitlab.com/locateit/oss-land-degradation-monitoring-service/oss-ldms/-/wikis/Forest-Carbon-Emissions
		"""
		##**********STEPS**************##
		"""
		1. Define Minimum Forest Unit (MFU) (Passed as a user specified param)
		2. Convert the Tree Cover Loss to a Forest Map
		"""
		"""
		- If user has drawn custom polygon, ignore the vector id
		since the custom polygon could span several shapefiles.
		- If no custom polygon is selected, demand an admin_level 
		and the vector id
		"""	
		transform = self.transform
		vector, error = self.get_vector()
		if error:
			return self.return_with_error(error)

		# # Validate that a raster type has been selected
		# raster_type = cint(raster_type)
		# if not raster_type:
		# 	return self.return_with_error(_("No raster type has been selected"))

		"""
		Validate analysis periods
		"""
		start_year, end_year, period_error = self.validate_periods()
		if period_error:
			return self.return_with_error(period_error)

		if self.enforce_single_year:
			if start_year != end_year:
				return self.return_with_error(_("Forest Carbon Emission can only be analysed for a single period"))

		# Get Raster Models	by period and raster type
		raster_models = get_raster_models(admin_zero_id=self.admin_0,
						raster_category=RasterCategoryEnum.TREE_COVER_LOSS.value,
						# raster_category=RasterCategoryEnum.LULC.value,
						raster_source=self.raster_source.value,
						raster_year__gte=start_year, 
						raster_year__lte=end_year)

		if not raster_models:
			return self.return_with_error(_("No matching rasters"))

		if self.enforce_single_year:
			if len(raster_models) > 1:
				return self.return_with_error(_("Multiple %s rasters exist for the selected period".format(RasterCategoryEnum.TREE_COVER_LOSS.value)))
		
		raster_model = raster_models[0]#get the first model		
		raster_path = get_media_dir() + raster_model.rasterfile.name
		# Validate existence of the raster file
		if not file_exists(raster_path):
			return self.return_with_error(_("Raster %s does not exist" % (raster_model.rasterfile.name)))
		 
		if raster_model.raster_year == start_year:
			forest_activity_raster, forest_activity_raster_path, nodata = clip_raster_to_vector_windowed(
			#tree_cover_loss_raster, tree_cover_loss_raster_path, nodata = clip_raster_to_vector(
					raster_file=raster_model.rasterfile.name,
					vector=vector, 
					window_size=(self.mfu, self.mfu),
					use_temp_dir=True, 
					apply_func=self.generate_forest_activity_map, 
					dest_nodata=ForestCarbonEmissionSettings.MFU_NODATA
			)

		change_matrix = self.initialize_forest_activity_map_matrix()
		# Transform the values
		df = pd.DataFrame({
						'baseline': forest_activity_raster.flatten(),
					})
		df['mapping'] = nodata

		# # Replace values
		# for row in change_matrix:
		# 	# filter all matching entries as per the matrix
		# 	mask = (df['baseline'] == row['key'])

		# 	valid = df[mask]

		# 	df.loc[mask, ['mapping']] = row['mapping']
		# 	df['mapping']=df['b'].apply(lambda x: 0 if x ==0 else math.log(x))
		# 	# (img[mask]*0.5)
		# 	# df['c']=df['b'].apply(lambda x: 0 if x ==0 else math.log(x))
		# 	df.loc[mask, ['mapping']] = valid['base'] / np.log(z_valid['b'])

		ton_per_ha = raster_model.resolution * 0.0001 # 1 square metre = 0.0001 ha
		results = []
		unique, counts = np.unique(forest_activity_raster, return_counts=True)			
		val_counts = dict(zip(unique, counts))
		for mapping in change_matrix:
			key = cint(mapping.get('key'))
			if key in val_counts:
				val = val_counts[mapping.get('key')]
				results.append({
					'change_type': key,
					'label': str(mapping.get('label')),
					'count': val,
					'area': val * raster_model.resolution,
					'co2': val * (mapping.get('factor') or 1) * ton_per_ha
				})
			else:
				results.append({
					'change_type': key,
					'label': str(mapping.get('label')),
					'count': 0,
					'area': 0,
					'co2': 0
				})
		
		datasource = df['mapping'].values.reshape(forest_activity_raster.shape)
		datasource = datasource.astype(np.int32)

		# hlper = RasterCalcHelper(vector=vector,
		# 			rasters=raster_models,
		# 			raster_type_id=raster_type,
		# 			stats=[],
		# 			is_categorical=True,
		# 			transform=transform)
		# res = hlper.get_stats()

		return return_raster_with_stats(
			request=self.request,
			datasource=forest_activity_raster, 
			prefix="carbon", 
			change_enum=ForestChangeTernaryEnum if ForestCarbonEmissionSettings.EXCLUDE_NOT_A_FOREST else ForestChangeQuinaryEnum, 
			metadata_raster_path=forest_activity_raster_path, #start_model.rasterfile.name, 
			nodata=nodata, 
			resolution=raster_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=ForestCarbonEmissionSettings.SUB_DIR,
			results=results #None #res
		)	

	def _calculate_carbon_emission_with_ready_activity_map(self):
		"""
		Compute Land Use Land Cover
		
		Returns:
			[Response]: [A JSON string with statistic values]
		"""    
		# self.analysis_type = LulcCalcEnum.LULC    
		vector_id = self.shapefile_id
		admin_level = self.admin_level
		raster_type = self.raster_type
		start_year = self.start_year
		end_year = self.end_year
		custom_coords = self.custom_vector_coords
		transform = self.transform
		
		"""
		- If user has drawn custom polygon, ignore the vector id
		since the custom polygon could span several shapefiles.
		- If no custom polygon is selected, demand an admin_level 
		and the vector id
		"""
		vector, error = self.get_vector()
		if error:
			return self.return_with_error(error)

		# Validate that a raster type has been selected
		# raster_type = cint(raster_type)
		# if not raster_type:
		# 	return self.return_with_error(_("No raster type has been selected"))

		"""
		Validate analysis periods
		"""
		start_year, end_year, period_error = self.validate_periods()
		if period_error:
			return self.return_with_error(period_error)

		if self.enforce_single_year:
			if start_year != end_year:
				return self.return_with_error(_("Forest Carbon Emission can only be analysed for a single period"))

		# Get Raster Models	by period and raster type
		raster_models = get_raster_models(admin_zero_id=self.admin_0,
						#raster_category=RasterCategoryEnum.TREE_COVER_LOSS.value,
						raster_category=RasterCategoryEnum.FOREST_ACTIVITY_MAP.value,
						raster_source=self.raster_source.value,
						raster_year__gte=start_year, 
						raster_year__lte=end_year)

		if not raster_models:
			return self.return_with_error(_("No matching rasters"))

		if self.enforce_single_year:
			if len(raster_models) > 1:
				return self.return_with_error(_("Multiple Tree Cover Loss rasters exist for the selected period"))

		for raster_model in raster_models:			
			# for raster_model in raster_models:
			raster_path = get_media_dir() + raster_model.rasterfile.name

			# Validate existence of the raster file
			if not file_exists(raster_path):
				return self.return_with_error(_("Raster %s does not exist" % (raster_model.rasterfile.name)))

			if raster_model.raster_year == start_year:
				lulc_raster, lulc_raster_path, nodata = clip_raster_to_vector(raster_model.rasterfile.name,
										 vector, 
										 dest_nodata=ForestCarbonEmissionSettings.MFU_NODATA)
			
		# hlper = RasterCalcHelper(vector=vector,
		# 			rasters=raster_models,
		# 			raster_type_id=raster_type,
		# 			stats=[],
		# 			is_categorical=True,
		# 			transform=transform)
		# res = hlper.get_stats()
		# return res

		change_matrix = self.initialize_forest_activity_map_matrix()
		# Transform the values
		df = pd.DataFrame({
						'baseline': lulc_raster.flatten(),
					})
		df['mapping'] = nodata

		# # Replace values
		# for row in change_matrix:
		# 	# filter all matching entries as per the matrix
		# 	mask = (df['baseline'] == row['key'])

		# 	valid = df[mask]

		# 	df.loc[mask, ['mapping']] = row['mapping']
		# 	df['mapping']=df['b'].apply(lambda x: 0 if x ==0 else math.log(x))
		# 	# (img[mask]*0.5)
		# 	# df['c']=df['b'].apply(lambda x: 0 if x ==0 else math.log(x))
		# 	df.loc[mask, ['mapping']] = valid['base'] / np.log(z_valid['b'])

		results = []
		unique, counts = np.unique(lulc_raster, return_counts=True)			
		val_counts = dict(zip(unique, counts))
		for mapping in change_matrix:
			key = cint(mapping.get('key'))
			if key in val_counts:
				val = val_counts[mapping.get('key')]
				results.append({
					'change_type': key,
					'label': str(mapping.get('label')),
					'count': val,
					'area': val * raster_model.resolution,
					'co2': val * (mapping.get('factor') or 1)
				})
			else:
				results.append({
					'change_type': key,
					'label': str(mapping.get('label')),
					'count': 0,
					'area': 0,
					'co2': 0
				})
		
		datasource = df['mapping'].values.reshape(lulc_raster.shape)
		datasource = datasource.astype(np.int32)

		return return_raster_with_stats(
			request=self.request,
			datasource=lulc_raster[0], # since its a (1, width, height) matrix
			prefix="carbon", 
			change_enum= ForestChangeTernaryEnum if ForestCarbonEmissionSettings.EXCLUDE_NOT_A_FOREST else ForestChangeQuinaryEnum, 
			metadata_raster_path=lulc_raster_path, 
			nodata=nodata, 
			resolution=raster_model.resolution,
			start_year=start_year,
			end_year=end_year,
			subdir=ForestCarbonEmissionSettings.SUB_DIR,
			results=results #None #res
		)

	def generate_forest_activity_map(self, array):
		"""
		Generate Forest Activity Map from the Tree Cover Loss

		Decision Rules are as below:

		1. First, any MFU with a percentage of no-data (ND) pixels higher than the tree cover
			threshold (3px) is classified as no-data (ND) and not taken into account in the
			deforestation/degradation areas estimates.
		2. any MFU with count of tree presence pixel below the tree cover
			threshold is classified as Non-Forest. Any loss of remaining tree pixels inside a MFU
			classified as Non-Forest is not taken into account in the estimates of emissions due to
			deforestation and forest degradation.
		3. any MFU with an initial count of tree presence pixel above or equal to the tree
			cover threshold (3px) belongs to a forest class. If no tree pixel loss was counted 
			in the MFU, the unit is classified as Forest.
		4. If some tree pixels are lost in the Period, the MFU is classified as deforestation or 
			forest degradation according to the remaining percentage of tree presence pixels (T-T). 
			A MFU is considered as degraded if the remaining percentage of tree cover after the
			two periods is above the minimum percentage required by the forest definition; 
			and deforested if the tree cover is lowered below this percentage.
		"""
		def get_key_val(key):
			return counts.get(key, 0)

		# get count of unique values
		vals, cnts = np.unique(array, return_counts=True)
		# get percentage count for each unique pixel value
		counts = dict(zip(vals, [x/sum(cnts) * 100 for x in cnts]))

		change = ForestCarbonEmissionSettings.NODATA
		if get_key_val(ForestCarbonEmissionSettings.NODATA) > self.mfu_forest_threshold:
			change = ForestCarbonEmissionSettings.NODATA if ForestCarbonEmissionSettings.EXCLUDE_NOT_A_FOREST else ForestCarbonEmissionSettings.NODATA
		elif get_key_val(ForestCoverLossQuinaryEnum.TREES_IN_BOTH_PERIODS.key) < self.mfu_forest_threshold:
			change = ForestCarbonEmissionSettings.NODATA if ForestCarbonEmissionSettings.EXCLUDE_NOT_A_FOREST else ForestChangeQuinaryEnum.NOT_FOREST.key
		elif get_key_val(ForestCoverLossQuinaryEnum.TREES_IN_BOTH_PERIODS.key) >= self.mfu_forest_threshold and \
			get_key_val(ForestCoverLossQuinaryEnum.TREE_LOSS_IN_PERIOD1.key) == 0 and \
			get_key_val(ForestCoverLossQuinaryEnum.TREE_LOSS_IN_PERIOD2.key) == 0:
			change = ForestChangeQuinaryEnum.UNDISTURBED_FOREST.key
		else:
			if get_key_val(ForestCoverLossQuinaryEnum.TREES_IN_BOTH_PERIODS) > self.mfu_forest_threshold:
				change = ForestChangeQuinaryEnum.DEGRADED_FOREST.key
			change = ForestChangeQuinaryEnum.DEFORESTED.key
		return np.array([[change]]) #ensure you return an ndarray

	def initialize_forest_activity_map_matrix(self):
		"""
		Initialize forest activity matrix
		"""
		matrix = [
			# {#0
			# 	'key': ForestChangeQuinaryEnum.NODATA.key,
			# 	'label': ForestChangeQuinaryEnum.NODATA.label,
			# 	'factor': 0
			# },
			{#1
				'key': ForestChangeQuinaryEnum.DEGRADED_FOREST.key,
				'label': ForestChangeQuinaryEnum.DEGRADED_FOREST.label,
				'factor': self.carbon_stock * (self.degradation_emission_proportion * 0.01) * ForestCarbonEmissionSettings.CO2_FACTOR
			},
			{#2
				'key': ForestChangeQuinaryEnum.DEFORESTED.key,
				'label': ForestChangeQuinaryEnum.DEFORESTED.label,
				'factor': self.carbon_stock * ForestCarbonEmissionSettings.CO2_FACTOR
			},
			{#3
				'key': ForestChangeQuinaryEnum.UNDISTURBED_FOREST.key,
				'label': ForestChangeQuinaryEnum.UNDISTURBED_FOREST.label,
				'factor': 0
			},
		]
		return matrix