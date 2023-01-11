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
from ldms.enums import (RasterSourceEnum, RasterOperationEnum, RasterCategoryEnum, 
						CVIEnum, CVIFactorsEnum, CVIComputationTypeEnum)
from ldms.utils.common_util import return_with_error, get_random_floats, cint, validate_years
from ldms.utils.file_util import (generate_file_name, get_absolute_media_path, get_download_url, 
								file_exists, get_physical_file_path_from_url)
from ldms import ModelNotExistError, AnalysisParamError
from django.conf import settings

MIN_INT = settings.MIN_INT #-9223372036854775807
MAX_INT = settings.MAX_INT # 9223372036854775807 

class CVISettings:
	SUB_DIR = "" # "cvi" # Subdirectory to store rasters for CVI
	LOW_BOUND = 0
	HIGH_BOUND = 1

class CoastalVulnerabilityIndex:
	"""
	Wrapper class for CVI (Coastal Vulnerability Index). 
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
		self.computation_type = kwargs.get('computation_type', None) # ILSWEComputationTypeEnum.ILSWE)
		self.kwargs = kwargs

	def calculate_cvi(self):
		"""
		Compute CVI
		
		Steps:
			1. Process and clip the input rasters
			2. Multiply the factors A = geomorphology * coastal_slope * sealevel_rise * shoreline_erosion * tide_range * wave_height
			3. Compute the Index (CVI)
			3. Color coding the CVI Map
		"""
		def get_reference_model():
			"""Get Model whose raster will be used to determine nodata val
			"""
			if self.computation_type == CVIComputationTypeEnum.GEOMORPHOLOGY:
				return geo_model 
			if self.computation_type == CVIComputationTypeEnum.COASTAL_SLOPE:
				return slope_model
			if self.computation_type == CVIComputationTypeEnum.SEALEVEL_CHANGE:
				return sealevel_model
			if self.computation_type == CVIComputationTypeEnum.SHORELINE_EROSION:
				return shoreline_model
			if self.computation_type == CVIComputationTypeEnum.TIDE_RANGE:
				return tide_model
			if self.computation_type == CVIComputationTypeEnum.WAVE_HEIGHT:
				return wave_model
			return None

		def does_rasterfile_exist(model):
			return file_exists(get_absolute_media_path(model.rasterfile.name), raise_exception=False)				

		if not isinstance(self.computation_type, CVIComputationTypeEnum):
			return self.return_with_error(_("Computation Type must be one of CVIComputationTypeEnum")) 	
		error, vector, geo_model, slope_model, sealevel_model, shoreline_model, tide_model, wave_model = self.prevalidate()
		if error:
			return self.return_with_error(error) 

		ref_model = get_reference_model()
		if ref_model and not does_rasterfile_exist(ref_model):
			return self.return_with_error(_("Raster file {0} does not exist".format(ref_model.rasterfile.name)))
		for mdl in [geo_model, slope_model, sealevel_model, shoreline_model, tide_model, wave_model]:
			if mdl and not does_rasterfile_exist(mdl):
				return self.return_with_error(_("Raster file {0} does not exist".format(mdl.rasterfile.name)))

		# Clip rasters
		nodata, clipped_rasters = clip_rasters(vector, 
										[geo_model, slope_model, sealevel_model, shoreline_model, tide_model, wave_model], 
										ref_model=ref_model,
										raise_file_missing_exception=self.computation_type == CVIComputationTypeEnum.CVI)
		
		# get the rasters and leave out the file
		clipped_raster_paths = [x[1] for x in clipped_rasters]
		clipped_rasters = [x[0] for x in clipped_rasters]
		# mask arrays to ensure nodata pixels are not considered
		clipped_rasters = mask_rasters(clipped_rasters, nodata)
		# geo_raster = clipped_rasters[0][0] 
		# coastal_slope_raster = clipped_rasters[1][0] 
		# sealevel_change_raster = clipped_rasters[2][0]
		# shoreline_erosion_raster = clipped_rasters[3][0]
		# mean_tide_raster = clipped_rasters[4][0]
		# mean_wave_raster = clipped_rasters[5][0]
		geo_raster = clipped_rasters[0]
		coastal_slope_raster = clipped_rasters[1]
		sealevel_change_raster = clipped_rasters[2]
		shoreline_erosion_raster = clipped_rasters[3]
		mean_tide_raster = clipped_rasters[4]
		mean_wave_raster = clipped_rasters[5]

		prefix = "cvi"
		change_enum = CVIFactorsEnum
		if self.computation_type == CVIComputationTypeEnum.GEOMORPHOLOGY:
			cvi = geo_raster
			prefix = "geo_"
		if self.computation_type == CVIComputationTypeEnum.COASTAL_SLOPE:
			cvi = coastal_slope_raster
			prefix = "cs_"
		if self.computation_type == CVIComputationTypeEnum.SEALEVEL_CHANGE:
			cvi = sealevel_change_raster
			prefix = "slc_"
		if self.computation_type == CVIComputationTypeEnum.SHORELINE_EROSION:
			cvi = shoreline_erosion_raster
			prefix = "sre_"
		if self.computation_type == CVIComputationTypeEnum.TIDE_RANGE:
			cvi = mean_tide_raster
			prefix = "mtr_"
		if self.computation_type == CVIComputationTypeEnum.WAVE_HEIGHT:
			cvi = mean_wave_raster
			prefix = "mwh_"
		if self.computation_type == CVIComputationTypeEnum.CVI:
			change_enum = CVIEnum
			# Multiply factors.
			rasters = reshape_rasters([geo_raster, coastal_slope_raster, sealevel_change_raster, shoreline_erosion_raster, mean_tide_raster, mean_wave_raster])
			cvi = np.sqrt((rasters[0] * rasters[1] * rasters[2] * rasters[3] * rasters[4] * rasters[5])/6)

		cvi = ma.array(cvi)		
		
		# Step 3
		matrix = self.initialize_matrix()
		df = pd.DataFrame({
						'ratio': cvi.filled(fill_value=nodata).flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']
		
		out_raster = df['mapping'].values.reshape(cvi.shape)
		out_raster = out_raster.astype(np.int32)
		resolution = geo_model.resolution if self.computation_type == CVIComputationTypeEnum.CVI else ref_model.resolution
		return return_raster_with_stats(
			request=self.request,
			datasource=out_raster[0], 
			prefix=prefix, 
			change_enum=change_enum, 
			metadata_raster_path=[x for x in clipped_raster_paths if x][0], #clipped_rasters[0][1],
			nodata=nodata, 
			resolution=resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=CVISettings.SUB_DIR
		)
	
	def prevalidate(self, both_valid=True):
		"""
		Do common prevalidations and processing

		Returns:
			A tuple	(error, vector, start_model, end_model, start_year, end_year)
		"""
		start_year, end_year, error = self.validate_periods(both_valid=both_valid)
		vector, error = self.get_vector()	
		geo_model, slope_model, sealevel_model, shoreline_model, tide_model, wave_model = None, None, None, None, None, None
		if not error:
			geo_model, slope_model, sealevel_model, shoreline_model, tide_model, wave_model, error = self.get_models(throw_error=self.computation_type == CVIComputationTypeEnum.CVI)

		return (error, vector, geo_model, slope_model, sealevel_model, shoreline_model, tide_model, wave_model)

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
		r_model, k_model, s_model, c_model, p_model, q_model = None, None, None, None, None, None
		error1, error2, error3, error4, error5, error6 = None, None, None, None, None, None
		if self.computation_type in [CVIComputationTypeEnum.GEOMORPHOLOGY, CVIComputationTypeEnum.CVI]:
			r_model, error1 = get_raster_model_by_category(RasterCategoryEnum.GEOMORPHOLOGY.value)

		if self.computation_type in [CVIComputationTypeEnum.COASTAL_SLOPE, CVIComputationTypeEnum.CVI]:
			k_model, error2 = get_raster_model_by_category(RasterCategoryEnum.COASTAL_SLOPE.value)

		if self.computation_type in [CVIComputationTypeEnum.SEALEVEL_CHANGE, CVIComputationTypeEnum.CVI]:
			s_model, error3 = get_raster_model_by_category(RasterCategoryEnum.SEALEVEL_CHANGE.value)

		if self.computation_type in [CVIComputationTypeEnum.SHORELINE_EROSION, CVIComputationTypeEnum.CVI]:
			c_model, error4 = get_raster_model_by_category(RasterCategoryEnum.SHORELINE_EROSION.value) 

		if self.computation_type in [CVIComputationTypeEnum.TIDE_RANGE, CVIComputationTypeEnum.CVI]:
			p_model, error5 = get_raster_model_by_category(RasterCategoryEnum.TIDE_RANGE.value) 

		if self.computation_type in [CVIComputationTypeEnum.WAVE_HEIGHT, CVIComputationTypeEnum.CVI]:
			q_model, error6 = get_raster_model_by_category(RasterCategoryEnum.WAVE_HEIGHT.value)
		return (r_model, k_model, s_model, c_model, p_model, q_model, error1 or error2 or error3 or error4 or error5 or error6)

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
		if self.computation_type == CVIComputationTypeEnum.GEOMORPHOLOGY:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 2,
					'mapping': CVIFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 2,
					'high': 3,
					'mapping': CVIFactorsEnum.LOW.key
				},
				{#3
					'low': 3,
					'high': 4,
					'mapping': CVIFactorsEnum.MODERATE.key
				},
				{#4
					'low': 4,
					'high': 5,
					'mapping': CVIFactorsEnum.HIGH.key
				},
				{#5
					'low': 5,
					'high': MAX_INT,
					'mapping': CVIFactorsEnum.VERY_HIGH.key
				},			
			] 
		if self.computation_type == CVIComputationTypeEnum.COASTAL_SLOPE:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0.6,
					'mapping': CVIFactorsEnum.VERY_HIGH.key
				},
				{#2
					'low': 0.6,
					'high': 0.9,
					'mapping': CVIFactorsEnum.HIGH.key
				},
				{#3
					'low': 0.9,
					'high': 1.3,
					'mapping': CVIFactorsEnum.MODERATE.key
				},
				{#4
					'low': 1.3,
					'high': 1.9,
					'mapping': CVIFactorsEnum.LOW.key
				},
				{#5
					'low': 1.9,
					'high': MAX_INT,
					'mapping': CVIFactorsEnum.VERY_LOW.key
				},			
			] 
		if self.computation_type == CVIComputationTypeEnum.SEALEVEL_CHANGE:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': -1.21,
					'mapping': CVIFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': -1.21,
					'high': 0.10,
					'mapping': CVIFactorsEnum.LOW.key
				},
				{#3
					'low': 0.1,
					'high': 1.24,
					'mapping': CVIFactorsEnum.MODERATE.key
				},
				{#4
					'low': 1.24,
					'high': 1.36,
					'mapping': CVIFactorsEnum.HIGH.key
				},
				{#5
					'low': 1.36,
					'high': MAX_INT,
					'mapping': CVIFactorsEnum.VERY_HIGH.key
				},			
			] 
		if self.computation_type == CVIComputationTypeEnum.SHORELINE_EROSION:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': -2.0,
					'mapping': CVIFactorsEnum.VERY_HIGH.key
				},
				{#2
					'low': -2.0,
					'high': -1.1,
					'mapping': CVIFactorsEnum.HIGH.key
				},
				{#3
					'low': -1.1,
					'high': 1.0,
					'mapping': CVIFactorsEnum.MODERATE.key
				},
				{#4
					'low': 1.0,
					'high': 2.0,
					'mapping': CVIFactorsEnum.LOW.key
				},
				{#5
					'low': 2.0,
					'high': MAX_INT,
					'mapping': CVIFactorsEnum.VERY_LOW.key
				},			
			] 
		if self.computation_type == CVIComputationTypeEnum.TIDE_RANGE:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 1.0,
					'mapping': CVIFactorsEnum.VERY_HIGH.key
				},
				{#2
					'low': 1.0,
					'high': 1.9,
					'mapping': CVIFactorsEnum.HIGH.key
				},
				{#3
					'low': 1.9,
					'high': 4.0,
					'mapping': CVIFactorsEnum.MODERATE.key
				},
				{#4
					'low': 4.0,
					'high': 6.0,
					'mapping': CVIFactorsEnum.LOW.key
				},
				{#5
					'low': 6.0,
					'high': MAX_INT,
					'mapping': CVIFactorsEnum.VERY_LOW.key
				},			
			] 
		if self.computation_type == CVIComputationTypeEnum.WAVE_HEIGHT:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 1.1,
					'mapping': CVIFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 1.1,
					'high': 2.0,
					'mapping': CVIFactorsEnum.LOW.key
				},
				{#3
					'low': 2.0,
					'high': 2.25,
					'mapping': CVIFactorsEnum.MODERATE.key
				},
				{#4
					'low': 2.25,
					'high': 2.60,
					'mapping': CVIFactorsEnum.HIGH.key
				},
				{#5
					'low': 2.60,
					'high': MAX_INT,
					'mapping': CVIFactorsEnum.VERY_HIGH.key
				},			
			] 
		if self.computation_type == CVIComputationTypeEnum.CVI:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 3.1623,
					'mapping': CVIEnum.VERY_LOW.key
				},
				{#2
					'low': 3.1623,
					'high': 4.0825,
					'mapping': CVIEnum.LOW.key
				},
				{#3
					'low': 4.0825,
					'high': 5.1640,
					'mapping': CVIEnum.MODERATE.key
				},
				{#4
					'low': 5.1640,
					'high': 7.0711,
					'mapping': CVIEnum.HIGH.key
				},
				{#5
					'low': 7.0711,
					'high': MAX_INT,
					'mapping': CVIEnum.VERY_HIGH.key
				},			
			] 		
		return matrix