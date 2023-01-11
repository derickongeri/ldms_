import numpy as np
import numpy.ma as ma
import pandas as pd
import tempfile
from django.utils.translation import gettext as _
from rest_framework.response import Response

from ldms.utils.vector_util import get_vector
from ldms.utils.raster_util import (get_raster_values, save_raster, reproject_raster, 
					do_raster_operation, get_raster_models, clip_raster_to_vector, clip_rasters,
					get_raster_meta, return_raster_with_stats, reshape_rasters, mask_rasters)
from ldms.enums import (RasterSourceEnum, RasterOperationEnum, RasterCategoryEnum, 
						ILSWEEnum, ILSWEFactorsEnum, ILSWEComputationTypeEnum)
from ldms.utils.common_util import return_with_error, get_random_floats, cint, validate_years
from ldms.utils.file_util import (generate_file_name, get_absolute_media_path, get_download_url, 
								file_exists, get_physical_file_path_from_url)
from ldms import ModelNotExistError, AnalysisParamError
from django.conf import settings
MIN_INT = settings.MIN_INT # -9223372036854775807
MAX_INT = settings.MAX_INT # 9223372036854775807 

class ILSWESettings:
	SUB_DIR = "" # "ilswe" # Subdirectory to store rasters for ILSWE
	LOW_BOUND = 0
	HIGH_BOUND = 1

class ILSWE:
	"""
	Wrapper class for ILSWE (Index of Land Susceptibility).
	Depends on CE (Climatic erosivity factor) and VC (Vegetation Cover) 
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

	def calculate_ilswe(self):
		"""
		Compute ILSWE
		
		Steps:
			1. Fuzzifying the inputs (Creating the sensitivity maps):
			2. Compute the Index of Land Susceptibility (ILSWE)
			3. Color coding the ILSWE Map for the ILSWE
		"""
		def get_reference_model():
			"""Get Model whose raster will be used to determine nodata val
			"""
			if self.computation_type == ILSWEComputationTypeEnum.VEGETATION_COVER:
				return vc_model 
			if self.computation_type == ILSWEComputationTypeEnum.SOIL_CRUST:
				return sc_model
			if self.computation_type == ILSWEComputationTypeEnum.SOIL_ROUGHNESS:
				return sr_model
			if self.computation_type == ILSWEComputationTypeEnum.ERODIBLE_FRACTION:
				return ef_model
			if self.computation_type == ILSWEComputationTypeEnum.CLIMATE_EROSIVITY:	
				return ce_model
			return None

		def does_rasterfile_exist(model):
			return file_exists(get_absolute_media_path(model.rasterfile.name), raise_exception=False)	

		if not isinstance(self.computation_type, ILSWEComputationTypeEnum):
			return self.return_with_error(_("Computation Type must be one of ILSWEComputationTypeEnum")) 	
		error, vector, vc_model, sr_model, sc_model, ef_model, ce_model = self.prevalidate()
		if error:
			return self.return_with_error(error) 
 
		ref_model = get_reference_model()
		if ref_model and not does_rasterfile_exist(ref_model):
			return self.return_with_error(_("Raster file {0} does not exist".format(ref_model.rasterfile.name)))

		for mdl in [vc_model, sr_model, sc_model, ef_model, ce_model]:
			if mdl and not does_rasterfile_exist(mdl):
				return self.return_with_error(_("Raster file {0} does not exist".format(mdl.rasterfile.name)))

		#nodata, clipped_rasters = self.clip_rasters(vector, [vc_model, sr_model, sc_model, ef_model, ce_model], ref_model=ref_model)
		nodata, clipped_rasters = clip_rasters(vector, 
										[vc_model, sr_model, sc_model, ef_model, ce_model], 
										ref_model=ref_model,
										raise_file_missing_exception=self.computation_type == ILSWEComputationTypeEnum.ILSWE)
		# vc_raster = clipped_rasters[0][0] 
		# sr_raster = clipped_rasters[1][0] 
		# sc_raster = clipped_rasters[2][0]
		# ef_raster = clipped_rasters[3][0]
		# ce_raster = clipped_rasters[4][0]

		clipped_raster_paths = [x[1] for x in clipped_rasters]
		clipped_rasters = [x[0] for x in clipped_rasters]
		# mask arrays to ensure nodata pixels are not considered
		#clipped_rasters = mask_rasters([x[0] for x in clipped_rasters], nodata)
		clipped_rasters = mask_rasters(clipped_rasters, nodata)
		vc_raster = clipped_rasters[0]
		sr_raster = clipped_rasters[1] 
		sc_raster = clipped_rasters[2]
		ef_raster = clipped_rasters[3]
		ce_raster = clipped_rasters[4]

		# Step 1
		vc_fuzz = self.fuzzify_vegetation_cover(vc_raster, nodata) if vc_raster.shape else None
		sr_fuzz = self.fuzzify_soil_roughness(sr_raster, nodata) if sr_raster.shape else None
		sc_fuzz = self.fuzzify_soil_crust(sc_raster, nodata) if sc_raster.shape else None
		ef_fuzz = self.fuzzify_erodible_fraction(ef_raster, nodata) if ef_raster.shape else None
		ce_fuzz = self.fuzzify_climatic_erosivity(ce_raster, nodata) if ce_raster.shape else None

		prefix = "ilswe"
		change_enum = ILSWEFactorsEnum
		# Step 2.			
		if self.computation_type == ILSWEComputationTypeEnum.VEGETATION_COVER:
			ilswe = vc_fuzz
			prefix = "vc_"
		if self.computation_type == ILSWEComputationTypeEnum.SOIL_CRUST:
			ilswe = sc_fuzz
			prefix = "sc_"
		if self.computation_type == ILSWEComputationTypeEnum.SOIL_ROUGHNESS:
			ilswe = sr_fuzz
			prefix = "sr_"
		if self.computation_type == ILSWEComputationTypeEnum.ERODIBLE_FRACTION:
			ilswe = ef_fuzz
			prefix = "ef_"
		if self.computation_type == ILSWEComputationTypeEnum.CLIMATE_EROSIVITY:
			ilswe = ce_fuzz
			prefix = "ce_"
		if self.computation_type == ILSWEComputationTypeEnum.ILSWE:
			change_enum = ILSWEEnum
			rasters = reshape_rasters([vc_fuzz, sr_fuzz, sc_fuzz, ef_fuzz, ce_fuzz])
			# multiply rasters
			ilswe = rasters[0] * rasters[1] * rasters[2] * rasters[3] * rasters[4]

		# Step 3
		matrix = self.initialize_matrix()
		df = pd.DataFrame({
						'ratio': ilswe.filled(fill_value=nodata).flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']
		
		out_raster = df['mapping'].values.reshape(ilswe.shape)
		out_raster = out_raster.astype(np.int32)
		resolution = vc_model.resolution if self.computation_type == ILSWEComputationTypeEnum.ILSWE else ref_model.resolution
		return return_raster_with_stats(
			request=self.request,
			datasource=out_raster[0], 
			prefix=prefix, 
			change_enum=change_enum, 
			metadata_raster_path=[x for x in clipped_raster_paths if x][0], #clipped_raster_paths[0], #clipped_rasters[0][1],
			nodata=nodata, 
			resolution=resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=ILSWESettings.SUB_DIR
		)

	def get_bounds(self, arry, nodata):
		"""Return the min and max vals

		Args:
			arry (ndarry): Array for whose to find max and min values

		Returns:
			tuple(min, max)
		"""
		# exclude nodata
		return np.amin(arry[arry != nodata]), np.amax(arry[arry != nodata])

	def apply_func(self, func, arry, nodata, switch_bounds=False):
		"""[summary]

		Args:
			func ([type]): [description]
			arry ([type]): [description]
			switch_bounds (bool, optional): [description]. Defaults to False.
		""" 
		ma_rast = ma.array(arry)		
		ma_rast[np.isnan(ma_rast)] = ma.masked #mask nan values
		# ma_rast[(ma_rast < ILSWESettings.LOW_BOUND) & (ma_rast != nodata)] = 0 # If values less than LOW_BOUND, set to 0
		ma_rast[ma_rast==nodata] = ma.masked #mask nodata values
		
		min, max = self.get_bounds(ma_rast, nodata)	
		if not switch_bounds:
			low_bound = min
			high_bound = max 
		else:
			low_bound = max
			high_bound = min 

		fuzz = func(ma_rast, low_bound, high_bound)
		return fuzz

	def linear_fuzzification(self, x, low_bound, high_bound):
		return (x - low_bound) / (high_bound - low_bound)
	
	def exponential_fuzzification(self, x, low_bound, high_bound):
		return np.power((x - low_bound) / (high_bound - low_bound), 2)
	
	def sigmoid_fuzzification(self, x, low_bound, high_bound):
		# cs = np.cos(((x - high_bound) / (low_bound - high_bound)) * (np.pi / 2))
		# cs = np.cos((1 - ((raster_array - low_bound) / (high_bound - low_bound))) * (np.pi / 2.0))
		cs = np.cos((1 - ((x - low_bound) / (high_bound - low_bound))) * (np.pi / 2.0))
		return np.power(cs, 2.0)

	def fuzzify_vegetation_cover(self, arry, nodata):
		"""VCfuzz is the Fuzzified VC, x is the pixel value of VC, low_bound = Max VC value and high_bound = min VC
		NOTE: Vegetation cover is monotonically decreasing hence the 
			low_bond = Max and NOT min. Also set all values of the pixels in the raster (VC values < 0)
			 that are less than zero to Zero

		Args:
			arry (ndarray): Array to fuzzify
			nodata (int): Nodata value
		"""
		# set all values of the pixels in the raster (VC values < 0) that are less than zero to Zero
		arry = np.where(arry >= 0, arry, 0)
		vc_fuzz = self.apply_func(self.exponential_fuzzification, arry, nodata, switch_bounds=True)		
		return vc_fuzz

	def fuzzify_soil_roughness(self, arry, nodata):
		"""SR_fuzz is the Fuzzified SC, x is the pixel value of SR, low_bound = Min SR value and high_bound = max SR
		Args:
			arry (ndarray): Array to fuzzify
			nodata (int): Nodata value
		"""
		sr_fuzz = self.apply_func(self.sigmoid_fuzzification, arry, nodata, switch_bounds=False)		
		return sr_fuzz

	def fuzzify_soil_crust(self, arry, nodata):
		""" SC_fuzz is the Fuzzified SC, x is the pixel value of SC, low_bound = Min SC value and high_bound = max SC
		Args:
			arry (ndarray): Array to fuzzify
			nodata (int): Nodata value
		"""
		sc_fuzz = self.apply_func(self.linear_fuzzification, arry, nodata, switch_bounds=False)	
		return sc_fuzz

	def fuzzify_erodible_fraction(self, arry, nodata):
		""" EF_fuzz is the Fuzzified EF, x is the pixel value of EF, low_bound = Min EF value and high_bound = max EF
		Args:
			arry (ndarray): Array to fuzzify
			nodata (int): Nodata value
		"""
		ef_fuzz = self.apply_func(self.linear_fuzzification, arry, nodata, switch_bounds=False)	
		return ef_fuzz
		
	def fuzzify_climatic_erosivity(self, arry, nodata):
		""" CE_fuzz is the Fuzzified CE, x is the pixel value of CE, low_bound = Min CE value and high_bound = max CE
		Args:
			arry (ndarray): Array to fuzzify
			nodata (int): Nodata value
		"""
		ce_fuzz = self.apply_func(self.linear_fuzzification, arry, nodata, switch_bounds=False)	
		return ce_fuzz

	def prevalidate(self, both_valid=True):
		"""
		Do common prevalidations and processing

		Returns:
			A tuple	(error, vector, start_model, end_model, start_year, end_year)
		"""
		start_year, end_year, error = self.validate_periods(both_valid=both_valid)
		vector, error = self.get_vector()	
		vc_model, sr_model, sc_model, ef_model, ce_model = None, None, None, None, None
		if not error:
			vc_model, sr_model, sc_model, ef_model, ce_model, error = self.get_models()

		return (error, vector, vc_model, sr_model, sc_model, ef_model, ce_model)

	def clip_rasters(self, vector, models, ref_model=None):
		"""Clip all rasters using the vector

		Args:
			vector (geojson): Polygon to be used for clipping
			models (List): Models whose raster files should be clipped
		
		Returns:
			tuple (nodata, list[raster, raster_file])
		"""
		res = []
		if not isinstance(models, list):
			models = [models]
		meta = get_raster_meta(ref_model.rasterfile.name) if ref_model else get_raster_meta(models[0].rasterfile.name)
		dest_nodata = meta['nodata']
		for i, model in enumerate(models):
			out_image, out_file, out_nodata = clip_raster_to_vector(model.rasterfile.name, 
											vector, use_temp_dir=True, 
											dest_nodata=dest_nodata)
			res.append([out_image, out_file])
		return (dest_nodata, res)

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
		vc_model, sr_model, sc_model, ef_model, ce_model = None, None, None, None, None
		error1, error2, error3, error4, error5 = None, None, None, None, None
		if self.computation_type in [ILSWEComputationTypeEnum.VEGETATION_COVER, ILSWEComputationTypeEnum.ILSWE]:
			vc_model, error1 = get_raster_model_by_category(RasterCategoryEnum.VEGETATION_COVER.value)
		if self.computation_type in [ILSWEComputationTypeEnum.SOIL_ROUGHNESS, ILSWEComputationTypeEnum.ILSWE]:
			sr_model, error2 = get_raster_model_by_category(RasterCategoryEnum.SOIL_ROUGHNESS.value)
		if self.computation_type in [ILSWEComputationTypeEnum.SOIL_CRUST, ILSWEComputationTypeEnum.ILSWE]:
			sc_model, error3 = get_raster_model_by_category(RasterCategoryEnum.SOIL_CRUST.value)
		if self.computation_type in [ILSWEComputationTypeEnum.ERODIBLE_FRACTION, ILSWEComputationTypeEnum.ILSWE]:
			ef_model, error4 = get_raster_model_by_category(RasterCategoryEnum.ERODIBLE_FRACTION.value)
		if self.computation_type in [ILSWEComputationTypeEnum.CLIMATE_EROSIVITY, ILSWEComputationTypeEnum.ILSWE]:
			ce_model, error5 = get_raster_model_by_category(RasterCategoryEnum.CLIMATIC_EROSIVITY.value)
		return (vc_model, sr_model, sc_model, ef_model, ce_model, error1 or error2 or error3 or error4 or error5)

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
		if self.computation_type == ILSWEComputationTypeEnum.VEGETATION_COVER:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0.4067,
					'mapping': ILSWEFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 0.4067,
					'high': 0.5147,
					'mapping': ILSWEFactorsEnum.LOW.key
				},
				{#3
					'low': 0.5147,
					'high': 0.5409,
					'mapping': ILSWEFactorsEnum.MODERATE.key
				},
				{#4
					'low': 0.5409,
					'high': 0.5585,
					'mapping': ILSWEFactorsEnum.HIGH.key
				},
				{#5
					'low': 0.5585,
					'high': MAX_INT,
					'mapping': ILSWEFactorsEnum.VERY_HIGH.key
				},
			] 
		if self.computation_type == ILSWEComputationTypeEnum.SOIL_CRUST:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0.1796,
					'mapping': ILSWEFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 0.1796,
					'high': 0.2001,
					'mapping': ILSWEFactorsEnum.LOW.key
				},
				{#3
					'low': 0.2001,
					'high': 0.2231,
					'mapping': ILSWEFactorsEnum.MODERATE.key
				},
				{#4
					'low': 0.2231,
					'high': 0.2566,
					'mapping': ILSWEFactorsEnum.HIGH.key
				},
				{#5
					'low': 0.2566,
					'high': MAX_INT,
					'mapping': ILSWEFactorsEnum.VERY_HIGH.key
				},
			] 
		if self.computation_type == ILSWEComputationTypeEnum.SOIL_ROUGHNESS:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0.2000,
					'mapping': ILSWEFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 0.2000,
					'high': 0.4000,
					'mapping': ILSWEFactorsEnum.LOW.key
				},
				{#3
					'low': 0.4000,
					'high': 0.6000,
					'mapping': ILSWEFactorsEnum.MODERATE.key
				},
				{#4
					'low': 0.6000,
					'high': 0.8000,
					'mapping': ILSWEFactorsEnum.HIGH.key
				},
				{#5
					'low': 0.8000,
					'high': MAX_INT,
					'mapping': ILSWEFactorsEnum.VERY_HIGH.key
				},
			] 
		if self.computation_type == ILSWEComputationTypeEnum.ERODIBLE_FRACTION:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0.3886,
					'mapping': ILSWEFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 0.3886,
					'high': 0.5264,
					'mapping': ILSWEFactorsEnum.LOW.key
				},
				{#3
					'low': 0.5264,
					'high': 0.6642,
					'mapping': ILSWEFactorsEnum.MODERATE.key
				},
				{#4
					'low': 0.6642,
					'high': 0.8020,
					'mapping': ILSWEFactorsEnum.HIGH.key
				},
				{#5
					'low': 0.8020,
					'high': MAX_INT,
					'mapping': ILSWEFactorsEnum.VERY_HIGH.key
				},
			] 
		if self.computation_type == ILSWEComputationTypeEnum.CLIMATE_EROSIVITY:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0.0719,
					'mapping': ILSWEFactorsEnum.VERY_LOW.key
				},
				{#2
					'low': 0.0719,
					'high': 0.1221,
					'mapping': ILSWEFactorsEnum.LOW.key
				},
				{#3
					'low': 0.1221,
					'high': 0.2404,
					'mapping': ILSWEFactorsEnum.MODERATE.key
				},
				{#4
					'low': 0.2404,
					'high': 0.3549,
					'mapping': ILSWEFactorsEnum.HIGH.key
				},
				{#5
					'low': 0.3549,
					'high': MAX_INT,
					'mapping': ILSWEFactorsEnum.VERY_HIGH.key
				},
			] 
		if self.computation_type == ILSWEComputationTypeEnum.ILSWE:
			matrix = [
				{#1
					'low': MIN_INT,
					'high': 0.0000,
					'mapping': ILSWEEnum.VERY_LOW.key
				},
				{#2
					'low': 0.0000,
					'high': 0.0023,
					'mapping': ILSWEEnum.LOW.key
				},
				{#3
					'low': 0.0023,
					'high': 0.0120,
					'mapping': ILSWEEnum.MODERATE.key
				},
				{#4
					'low': 0.0120,
					'high': 0.0265,
					'mapping': ILSWEEnum.HIGH.key
				},
				{#5
					'low': 0.0265,
					'high': MAX_INT,
					'mapping': ILSWEEnum.VERY_HIGH.key
				},
			] 
		return matrix