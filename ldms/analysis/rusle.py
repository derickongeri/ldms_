import numpy as np
import numpy.ma as ma
import pandas as pd
import tempfile
from django.utils.translation import gettext as _
from rest_framework.response import Response

from ldms.utils.vector_util import get_vector
from ldms.utils.raster_util import (get_raster_values, save_raster, reproject_raster, 
					do_raster_operation, get_raster_models, clip_raster_to_vector,
					clip_rasters, mask_rasters,
					get_raster_meta, return_raster_with_stats, reshape_rasters)
from ldms.enums import (RasterSourceEnum, RasterOperationEnum, 
						RasterCategoryEnum, RUSLEEnum, RUSLEComputationTypeEnum, RUSLEFactorsEnum)
from ldms.utils.common_util import return_with_error, get_random_floats, cint, validate_years
from ldms.utils.file_util import (generate_file_name, get_absolute_media_path, get_download_url, 
								file_exists, get_physical_file_path_from_url)
from ldms import ModelNotExistError, AnalysisParamError
from ldms.utils.raster_util import RasterCalcHelper
from django.conf import settings

MIN_INT = settings.MIN_INT # -9223372036854775807
MAX_INT = settings.MAX_INT # 9223372036854775807 

class RUSLESettings:
	SUB_DIR = "" # "rusle" # Subdirectory to store rasters for ILSWE
	
class RUSLE:
	"""
	Wrapper class for RUSLE (Revised Universal Soil Loss Equation).
	Depends on Rainfall erosivity (R-factor), soil erodibility(K-factor), 
	slope steepness(S-factor), Cover management (C-factor) and Conservation practices (P-factor)
	"""	    
	def __init__(self, **kwargs):
		"""
		Args:
			admin_level (int): 
				The administrative level for the polygon to be used in case a shapefile id has been provided for the parameter **vector**.
			shapefile_id (int): 
				ID of an existing shapefile. 
			custom_coords (GeoJSON, or GEOSGeometry): 
				Coordinates which may be as a result of a custom drawn polygon or a Geometry object in form of GeoJSON.
			raster_type (int):  
				The type of raster files to be used
			start_year (int): 
				Historical period to which to compare recent primary productivity 
			end_year (int): 
				End year for which raster files should be used. 
			end_year (int): 
				End year for which raster files should be used. 
			comparison_periods (int): 
				Recent years used to compute comparison
			computation_type (string):
				Type of computation to be returned. Must be one of RUSLEComputationTypeEnum
			transform (string):
				Either of:
					- "area"
					- a string with placeholder e.g x * x to mean square of that value
			request (Request): 
				A Web request object
		""" 
		self.admin_level = kwargs.get('admin_level', None)
		self.shapefile_id = kwargs.get('shapefile_id', None)
		self.custom_vector_coords = kwargs.get('custom_vector_coords', None)
		self.raster_type = kwargs.get('raster_type', None)
		self.start_year = kwargs.get('start_year', None)
		self.end_year = kwargs.get('end_year', None)
		self.transform = kwargs.get('transform', "area")
		self.request = kwargs.get('request', None)
		self.error = None
		self.analysis_type = None #one of ProductivityCalcEnum		
		# self.reference_eco_units = kwargs.get('reference_eco_units', None)
		# self.reference_soc = kwargs.get('reference_soc', None)
		self.raster_source = kwargs.get('raster_source', RasterSourceEnum.MODIS)
		self.admin_0 = kwargs.get('admin_0', None)
		# self.veg_index = kwargs.get('veg_index', RasterCategoryEnum.VC.value)
		self.computation_type = kwargs.get('computation_type', None) # RUSLEComputationTypeEnum.RUSLE)
		self.kwargs = kwargs 

	def calculate_rusle(self):
		"""
		Compute RUSLE
		
		Steps:
			1. Process and clip the input rasters
			2. Multiply the factors A = R * K * S * C * P
			3. Compute the Index (RUSLE)
			3. Color coding the RUSLE Map
		"""
		if not isinstance(self.computation_type, RUSLEComputationTypeEnum):
			return self.return_with_error(_("Computation Type must be one of RUSLEComputationTypeEnum")) 	
		error, vector, r_model, k_model, s_model, c_model, p_model = self.prevalidate()
		if error:
			return self.return_with_error(error) 
		# Clip rasters
		nodata, clipped_rasters = clip_rasters(vector, [r_model, k_model, s_model, c_model, p_model])
		# r_raster = clipped_rasters[0][0] 
		# k_raster = clipped_rasters[1][0] 
		# s_raster = clipped_rasters[2][0]
		# c_raster = clipped_rasters[3][0]
		# p_raster = clipped_rasters[4][0]
		clipped_raster_paths = [x[1] for x in clipped_rasters]
		# mask arrays to ensure nodata pixels are not considered
		clipped_rasters = mask_rasters([x[0] for x in clipped_rasters], nodata)
		r_raster = clipped_rasters[0]
		k_raster = clipped_rasters[1]
		s_raster = clipped_rasters[2]
		c_raster = clipped_rasters[3]
		p_raster = clipped_rasters[4]

		prefix = "rusle"
		change_enum = RUSLEFactorsEnum
		if self.computation_type == RUSLEComputationTypeEnum.RAINFALL_EROSIVITY:
			rusle = r_raster
			prefix = "r_"
		if self.computation_type == RUSLEComputationTypeEnum.SOIL_ERODIBILITY:
			rusle = k_raster
			prefix = "k_"
		if self.computation_type == RUSLEComputationTypeEnum.SLOPE_STEEPNESS:
			rusle = s_raster
			prefix = "s_"
		if self.computation_type == RUSLEComputationTypeEnum.COVER_MANAGEMENT:
			rusle = c_raster
			prefix = "c_"
		if self.computation_type == RUSLEComputationTypeEnum.CONSERVATION_PRACTICES:
			rusle = p_raster
			prefix = "p_"
		if self.computation_type == RUSLEComputationTypeEnum.RUSLE:
			change_enum = RUSLEEnum
			# Multiply factors.
			rasters = reshape_rasters([r_raster, k_raster, s_raster, c_raster, p_raster])
			rusle = rasters[0] * rasters[1] * rasters[2] * rasters[3] * rasters[4]

		rusle = ma.array(rusle)		
		
		# Step 3
		matrix = self.initialize_matrix()
		df = pd.DataFrame({
						'ratio': rusle.filled(fill_value=nodata).flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']
		
		out_raster = df['mapping'].values.reshape(rusle.shape)
		out_raster = out_raster.astype(np.int32)

		return return_raster_with_stats(
			request=self.request,
			datasource=out_raster[0], 
			prefix=prefix, 
			change_enum=change_enum, 
			metadata_raster_path=clipped_raster_paths[0], #clipped_rasters[0][1],
			nodata=nodata, 
			resolution=r_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=RUSLESettings.SUB_DIR
		)
	
	def return_input_rasters(self, vector, raster, raster_model, 
					raster_type, nodata, metadata_raster_path, transform="area"):
		"""Return input rasters

		Args:
			raster (array): Input raster
		"""
		# hlper = RasterCalcHelper(vector=vector,
		# 			rasters=[raster],
		# 			raster_type_id=raster_type,
		# 			stats=[],
		# 			is_categorical=True,
		# 			transform=transform)
		# res = hlper.get_stats()
		# return res
		return return_raster_with_stats(
			request=self.request,
			datasource=raster,
			prefix="rusle", 
			change_enum=RUSLEEnum, 
			metadata_raster_path=metadata_raster_path, 
			nodata=nodata, 
			resolution=raster_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=RUSLESettings.SUB_DIR,
			# results=res
		)

	def prevalidate(self, both_valid=True):
		"""
		Do common prevalidations and processing

		Returns:
			A tuple	(error, vector, start_model, end_model, start_year, end_year)
		"""
		start_year, end_year, error = self.validate_periods(both_valid=both_valid)
		vector, error = self.get_vector()	
		r_model, k_model, s_model, c_model, p_model = None, None, None, None, None
		if not error:
			r_model, k_model, s_model, c_model, p_model, error = self.get_models()

		return (error, vector, r_model, k_model, s_model, c_model, p_model)

	# def clip_rasters(self, vector, models):
	# 	"""Clip all rasters using the vector

	# 	Args:
	# 		vector (geojson): Polygon to be used for clipping
	# 		models (List): Models whose raster files should be clipped
		
	# 	Returns:
	# 		tuple (nodata, list[raster, raster_file])
	# 	"""
	# 	res = []
	# 	if not isinstance(models, list):
	# 		models = [models]
	# 	meta = get_raster_meta(models[0].rasterfile.name)
	# 	dest_nodata = meta['nodata']
	# 	for i, model in enumerate(models):
	# 		out_image, out_file, out_nodata = clip_raster_to_vector(model.rasterfile.name, 
	# 										vector, use_temp_dir=True, 
	# 										dest_nodata=dest_nodata)
	# 		res.append([out_image, out_file])
	# 	return (dest_nodata, res)

	def validate_periods(self, both_valid=False):
		"""
		Validate the start and end periods

		Returns:
			tuple (Start_Year, End_Year)
		"""		
		start_year = self.start_year
		end_year = self.end_year

		return validate_years(
							start_year=start_year,
							end_year=end_year,
							both_valid=both_valid)

	def get_models(self, throw_error=False):
		"""
		Get all the required models
		"""
		def get_raster_model_by_category(raster_category):
			model = get_raster_models(raster_year=year, 
								raster_source=self.raster_source.value,
								raster_category=raster_category, 
								admin_zero_id=self.admin_0
							).first()
			error = None
			if not model:
				error = _("Year {0} does not have an associated {1} {2} raster{3}.".format(year, 
								raster_category,
								self.raster_source.value, 
								" for the selected country" if self.admin_0 else ""))
				if throw_error:
					raise ModelNotExistError(error)
			return (model, error)

		year = self.end_year
		r_model, error1 = get_raster_model_by_category(RasterCategoryEnum.RAINFALL_EROSIVITY.value)
		k_model, error2 = get_raster_model_by_category(RasterCategoryEnum.SOIL_ERODIBILITY.value)
		s_model, error3 = get_raster_model_by_category(RasterCategoryEnum.SLOPE_STEEPNESS.value)
		c_model, error4 = get_raster_model_by_category(RasterCategoryEnum.COVER_MANAGEMENT.value)
		p_model, error5 = get_raster_model_by_category(RasterCategoryEnum.CONSERVATION_PRACTICES.value)
		return (r_model, k_model, s_model, c_model, p_model, error1 or error2 or error3 or error4 or error5)

	def get_vector(self):
		return get_vector(admin_level=self.admin_level, 
						  shapefile_id=self.shapefile_id, 
						  custom_vector_coords=self.custom_vector_coords, 
						  admin_0=self.admin_0,
						  request=self.request)

	def return_with_error(self, error):		
		self.error = error
		return return_with_error(self.request, error)

	def initialize_matrix(self):
		if self.computation_type == RUSLEComputationTypeEnum.RAINFALL_EROSIVITY:
			# r factor
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 60,
					'mapping': RUSLEFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 60,
					'high': 90,
					'mapping': RUSLEFactorsEnum.LOW.key
				},
				{#3
					'low': 90,
					'high': 120,
					'mapping': RUSLEFactorsEnum.MEDIUM.key
				},
				{#4
					'low': 120,
					'high': 160,
					'mapping': RUSLEFactorsEnum.HIGH.key
				},
				{#5
					'low': 160,
					'high': MAX_INT,
					'mapping': RUSLEFactorsEnum.VERY_HIGH.key
				},			
			] 
		if self.computation_type == RUSLEComputationTypeEnum.SOIL_ERODIBILITY:
			# k factor
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0.25,
					'mapping': RUSLEFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 0.25,
					'high': 0.65,
					'mapping': RUSLEFactorsEnum.LOW.key
				},
				{#3
					'low': 0.65,
					'high': 1.0,
					'mapping': RUSLEFactorsEnum.MEDIUM.key
				},
				{#4
					'low': 1.0,
					'high': 1.5,
					'mapping': RUSLEFactorsEnum.HIGH.key
				},
				{#5
					'low': 1.5,
					'high': MAX_INT,
					'mapping': RUSLEFactorsEnum.VERY_HIGH.key
				},			
			] 
		if self.computation_type == RUSLEComputationTypeEnum.SLOPE_STEEPNESS:
			# S factor
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0,
					'mapping': RUSLEFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 0,
					'high': 5,
					'mapping': RUSLEFactorsEnum.LOW.key
				},
				{#3
					'low': 5,
					'high': 10,
					'mapping': RUSLEFactorsEnum.MEDIUM.key
				},
				{#4
					'low': 10,
					'high': 15,
					'mapping': RUSLEFactorsEnum.HIGH.key
				},
				{#5
					'low': 15,
					'high': MAX_INT,
					'mapping': RUSLEFactorsEnum.VERY_HIGH.key
				},			
			] 
		if self.computation_type == RUSLEComputationTypeEnum.COVER_MANAGEMENT:
			# c factor
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0.1,
					'mapping': RUSLEFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 0.1,
					'high': 0.2,
					'mapping': RUSLEFactorsEnum.LOW.key
				},
				{#3
					'low': 0.2,
					'high': 0.3,
					'mapping': RUSLEFactorsEnum.MEDIUM.key
				},
				{#4
					'low': 0.3,
					'high': 0.4,
					'mapping': RUSLEFactorsEnum.HIGH.key
				},
				{#5
					'low': 0.4,
					'high': MAX_INT,
					'mapping': RUSLEFactorsEnum.VERY_HIGH.key
				},			
			] 
		if self.computation_type == RUSLEComputationTypeEnum.CONSERVATION_PRACTICES:
			# p factor
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0.1,
					'mapping': RUSLEFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 0.1,
					'high': 0.3,
					'mapping': RUSLEFactorsEnum.LOW.key
				},
				{#3
					'low': 0.3,
					'high': 0.5,
					'mapping': RUSLEFactorsEnum.MEDIUM.key
				},
				{#4
					'low': 0.5,
					'high': 0.8,
					'mapping': RUSLEFactorsEnum.HIGH.key
				},
				{#5
					'low': 0.8,
					'high': MAX_INT,
					'mapping': RUSLEFactorsEnum.VERY_HIGH.key
				},			
			] 
		if self.computation_type == RUSLEComputationTypeEnum.RUSLE:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 2,
					'mapping': RUSLEEnum.VERY_SLIGHT.key
				},
				{#2
					'low': 2,
					'high': 10,
					'mapping': RUSLEEnum.SLIGHT.key
				},
				{#3
					'low': 10,
					'high': 20,
					'mapping': RUSLEEnum.MODERATE.key
				},
				{#4
					'low': 20,
					'high': 50,
					'mapping': RUSLEEnum.HIGH.key
				},
				{#5
					'low': 50,
					'high': MAX_INT,
					'mapping': RUSLEEnum.VERY_HIGH.key
				},			
			] 		
		return matrix