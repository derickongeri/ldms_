import rasterio
import numpy as np
import numpy.ma as ma
import pandas as pd
import enum
from django.utils.translation import gettext as _
from rest_framework.response import Response
from ldms.utils.raster_util import (extract_pixels_using_vector, get_raster_meta, clip_raster_to_vector,
				return_raster_with_stats, do_raster_operation,
				get_raster_meta, clip_raster_to_vector,
				reshape_raster, reshape_rasters, reproject_raster, get_raster_values,
				harmonize_raster_nodata, get_raster_models)
from ldms.enums import (AridityIndexEnum, RasterCategoryEnum, RasterSourceEnum, 
					RasterOperationEnum, ClimateQualityIndexEnum,
					SoilQualityIndexEnum, SoilSlopeIndexEnum,
					SoilGroupIndexEnum, SoilDrainageIndexEnum,
					SoilParentMaterialEnum, SoilTextureEnum,
					SoilRockFragmentEnum, ManagementQualityIndexEnum, 
					VegetationQualityEnum, GenericRasterBandEnum, ESAIEnum)
from ldms.utils.vector_util import get_vector
from ldms import ModelNotExistError, AnalysisParamError
from ldms.utils.common_util import cint, return_with_error, validate_years
from django.conf import settings
from rasterio.warp import Resampling
from ldms.utils.file_util import (get_physical_file_path_from_url)

MIN_INT = settings.MIN_INT # -9223372036854775807
MAX_INT = settings.MAX_INT # 9223372036854775807 

class MedalusSettings:
	# DEFAULT_NODATA = 255 # default value of nodata
	SUB_DIR = "" # "degr" # Subdirectory to store rasters for degradation

class Medalus:
	"""
	Wrapper class for Medalus Indicies.	
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
		self.raster_source = kwargs.get('raster_source', RasterSourceEnum.MODIS)
		self.admin_0 = kwargs.get('admin_0', None)

		self.BASE_RESAMPLING_PATH = None # Base resampling path that should be used to reproject other rasters
		
		self.settings = MedalusSettings()

	def resample(self, reference_raster, raster_file, vector, nodata):
		"""
		Will resample to a common raster if BASE_RESAMPLING_PATH is defined. Else, just clip the raster
		"""		
		ref_raster = reference_raster or self.BASE_RESAMPLING_PATH
		if ref_raster:
			reprojected_raster_file, nodata = reproject_raster(reference_raster=reference_raster or self.BASE_RESAMPLING_PATH, 
												raster=raster_file,
												resampling=Resampling.nearest)
		else:
			reprojected_raster_file = raster_file
		# Clip the raster
		raster, nodata, raster_path = extract_pixels_using_vector(reprojected_raster_file, vector)
		return (raster, nodata, raster_path)

	def validate_periods(self):
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
							both_valid=False)

	def calculate_aridity_index(self, return_raster=False, resampling_raster=None):
		"""
		Compute Aridity Index (AI)
		Aridity Index = Mean_annual_precipication(MAP) / Mean_annual_evapotranspiration 
		Args:
			return_raster (bool): If True, raw raster will be returned instead of computed statistics
		"""
		start_year, end_year, error = self.validate_periods()
		
		vector, error = self.get_vector()	
		if error:
			return self.return_with_error(error)

		map_model, mae_model, error = self.get_ai_raster_models()
		if error:
			return self.return_with_error(error)

		# Extract MAP raster meta data
		map_meta = get_raster_meta(map_model.rasterfile.name)
		nodata = map_meta['nodata'] 
		
		# Clip the raster
		# Resampling will use self.BASE_RESAMPLING_PATH if it exists
		map_meta_raster, nodata, map_meta_raster_path = self.resample(reference_raster=resampling_raster, 
																	  raster_file=map_model.rasterfile.name, 
																	  vector=vector, nodata=nodata)
		# Extract MAE Raster
		mae_meta = get_raster_meta(mae_model.rasterfile.name)		
		
		"""
		Reproject ndvi_start_raster, ndvi_end_raster and soil_grid_raster based on base_lc_cover raster
		"""
		# reproject soil raster to modis resolution
		
		# Do `resampling_raster or map_model` so that it picks resampling_raster first if any as the reference raster
		mae_meta_raster, nodata, mae_meta_raster_path = self.resample(reference_raster=resampling_raster or map_model.rasterfile.name, 
																raster_file=mae_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		ratios = do_raster_operation([map_meta_raster, mae_meta_raster], RasterOperationEnum.DIVIDE, nodata)

		self.initialize_aridity_matrix()

		df = pd.DataFrame({
						'ratio': ratios.filled(fill_value=nodata).flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in self.aridity_matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high']) & (df['ratio'] != nodata)
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']

		datasource = df['mapping'].values.reshape(ratios.shape)
		datasource = datasource.astype(np.int32)
		
		self.ratios = ratios # just for unit testing purposes
		if return_raster:
			return datasource
		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="ai", 
			change_enum=AridityIndexEnum, 
			metadata_raster_path=map_meta_raster_path,  
			nodata=nodata, 
			resolution=map_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=MedalusSettings.SUB_DIR
		)
	
	def calculate_climate_quality_index(self, resampling_raster=None):
		return self.calculate_climate_quality_index_without_aspect(resampling_raster)

	def calculate_climate_quality_index_without_aspect(self, resampling_raster=None):
		"""
		Calculate Climate Quality Index (CQI)
		CQI = power(Aridity Index x Rainfall, 1/2)		
		"""		
		start_year, end_year, error = self.validate_periods()
		
		vector, error = self.get_vector()	
		if error:
			return self.return_with_error(error)

		aridity_model, rain_model, error = self.get_cqi_raster_models(include_aspect=False)
		if error:
			return self.return_with_error(error)
	
		# Extract MAP raster meta data
		# rain_meta = get_raster_meta(rain_model.rasterfile.name)
		# nodata = rain_meta['nodata']
		meta = get_raster_meta(resampling_raster or aridity_model.rasterfile.name)
		nodata = meta['nodata']

		# Clip the raster		
		aridity_raster, _, aridity_raster_path = self.resample(reference_raster=resampling_raster, 
																raster_file=aridity_model.rasterfile.name, 
																vector=vector, nodata=nodata)	

		# Resampling will use self.BASE_RESAMPLING_PATH if it exists
		rain_meta_raster, _, rain_meta_raster_path = self.resample(reference_raster=resampling_raster or aridity_model.rasterfile.name, 
																raster_file=rain_model.rasterfile.name, 
																vector=vector, nodata=nodata)		
		
		# self.initialize_rainfall_reclassification_matrix()
		
		# """Replace the values of rainfall by an index as specified in the self.rainfall_matrix"""
		# df = pd.DataFrame({
		# 				'ratio': rain_meta_raster.flatten(),												
		# 			})
		# df['mapping'] = nodata
		# # Replace values
		# for row in self.rainfall_matrix:
		# 	# filter all matching entries as per the matrix
		# 	mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high']) & (df['ratio'] != nodata)
		# 	df.loc[mask, ['mapping']] = row['mapping']

		# reclassed_rainfall = df['mapping'].values.reshape(rain_meta_raster.shape)
		# reclassed_rainfall = reclassed_rainfall.astype(np.int32)

		reclassed_rainfall = rain_meta_raster

		# compute AI
		# ai_raster = self.calculate_aridity_index(return_raster=True, resampling_raster=resampling_raster)
		# if self.error:
		# 	return self.return_with_error(self.error)

		ai_raster = aridity_raster

		"""compute cqi
		CQI = power(R * AI, 1/2)
		"""
		#initialize a masked array to allow for multiplying of only valid data
		ma_rainfall = ma.array(reclassed_rainfall.astype(float)) #initialize a masked array
		ma_ai_raster = ma.array(ai_raster.astype(float))
		
		ma_rainfall[ma_rainfall==nodata] = ma.masked
		ma_ai_raster[ma_ai_raster==nodata] = ma.masked
		
		cqi = np.power(np.multiply(ma_rainfall.astype(float), ma_ai_raster.astype(float)), 1/2)

		self.initialize_cqi_matrix()

		df = pd.DataFrame({
						'ratio': cqi.flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in self.cqi_matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']
		
		datasource = df['mapping'].values.reshape(cqi.shape)
		datasource = datasource.astype(np.int32)
		
		extras = {'raw_raster': str(cqi.tolist())}
		# self.ratios = ratios # just for unit testing purposes
		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="cqi", 
			change_enum=ClimateQualityIndexEnum, 
			metadata_raster_path=rain_meta_raster_path,  
			nodata=nodata, 
			resolution=rain_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=MedalusSettings.SUB_DIR,
			extras=extras
		)

	def calculate_climate_quality_index_with_aspect(self, resampling_raster=None):
		"""
		Calculate Climate Quality Index (CQI)
		CQI = pow(R * AI * A, 1/3)
		Where:
			R = Rainfall, AI=Aridity Index, A=Aspect			
		"""		
		start_year, end_year, error = self.validate_periods()
		
		vector, error = self.get_vector()	
		if error:
			return self.return_with_error(error)

		aridity_model, rain_model, aspect_model, error = self.get_cqi_raster_models()
		if error:
			return self.return_with_error(error)

		# Extract MAP raster meta data
		rain_meta = get_raster_meta(resampling_raster or rain_model.rasterfile.name)
		nodata = rain_meta['nodata']
		
		# Clip the raster		
		# Resampling will use self.BASE_RESAMPLING_PATH if it exists
		rain_meta_raster, _, rain_meta_raster_path = self.resample(reference_raster=resampling_raster, 
																raster_file=rain_model.rasterfile.name, 
																vector=vector, nodata=nodata)
																
		# Extract MAE Raster
		aspect_meta = get_raster_meta(aspect_model.rasterfile.name)
		# nodata = aspect_meta['nodata']		
		
		"""
		Reproject ndvi_start_raster, ndvi_end_raster and soil_grid_raster based on base_lc_cover raster
		"""
		# reproject soil raster to modis resolution
		
		# Do `resampling_raster or slope_model` so that it picks resampling_raster first if any as the reference raster
		aspect_meta_raster, _, aspect_meta_raster_path = self.resample(reference_raster=resampling_raster or rain_model.rasterfile.name, 
																raster_file=aspect_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		# Do `resampling_raster or slope_model` so that it picks resampling_raster first if any as the reference raster
		aridity_raster, _, aridity_meta_raster_path = self.resample(reference_raster=resampling_raster or rain_model.rasterfile.name, 
																raster_file=aridity_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		self.initialize_rainfall_reclassification_matrix()
		
		"""Replace the values of rainfall by an index as specified in the self.rainfall_matrix"""
		df = pd.DataFrame({
						'ratio': rain_meta_raster.flatten(),												
					})
		df['mapping'] = nodata
		# Replace values
		for row in self.rainfall_matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high']) & (df['ratio'] != nodata)
			df.loc[mask, ['mapping']] = row['mapping']

		reclassed_rainfall = df['mapping'].values.reshape(rain_meta_raster.shape)
		reclassed_rainfall = reclassed_rainfall.astype(np.int32)

		# compute AI
		# ai_raster =  self.calculate_aridity_index(return_raster=True)
		# if self.error:
		# 	return self.return_with_error(self.error)
		ai_raster = aridity_raster

		"""compute cqi
		CQI = power(R * AI * A, 1/3)
		"""
		#initialize a masked array to allow for multiplying of only valid data
		ma_rainfall = ma.array(reclassed_rainfall.astype(float)) #initialize a masked array
		ma_ai_raster = ma.array(ai_raster.astype(float))
		ma_aspect_meta_raster = ma.array(aspect_meta_raster.astype(float))

		ma_rainfall[ma_rainfall==nodata] = ma.masked
		ma_ai_raster[ma_ai_raster==nodata] = ma.masked
		ma_aspect_meta_raster[ma_aspect_meta_raster==nodata] = ma.masked

		cqi = np.power(np.multiply(ma_rainfall.astype(float), ma_ai_raster.astype(float), ma_aspect_meta_raster.astype(float)), 1/3)

		self.initialize_cqi_matrix()

		df = pd.DataFrame({
						'ratio': cqi.flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in self.cqi_matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']
		
		datasource = df['mapping'].values.reshape(cqi.shape)
		datasource = datasource.astype(np.int32)
				
		# self.ratios = ratios # just for unit testing purposes
		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="cqi", 
			change_enum=ClimateQualityIndexEnum, 
			metadata_raster_path=rain_meta_raster_path,  
			nodata=nodata, 
			resolution=rain_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=MedalusSettings.SUB_DIR 
		)

	def calculate_soil_quality_index(self, resampling_raster=None):
		"""
		Calculate Soil Quality Index (SQI)
		SQI = texture * parent_material * rock_fragment * depth * slope * drainage
		"""
		start_year, end_year, error = self.validate_periods()		
		vector, error = self.get_vector()	
		if error:
			return self.return_with_error(error)

		slope_model, depth_model, drainage_model, parentmaterial_model, texture_model, rockfragment_model, error = self.get_sqi_raster_models()
		if error:
			return self.return_with_error(error)

		# Extract Slope raster meta data
		slope_meta = get_raster_meta(resampling_raster or slope_model.rasterfile.name)
		nodata = slope_meta['nodata']
		# Clip the raster
		
		# Resampling will use self.BASE_RESAMPLING_PATH if it exists
		slope_raster, _, slope_raster_path = self.resample(reference_raster=resampling_raster, 
																raster_file=slope_model.rasterfile.name, 
																vector=vector, nodata=nodata)
		"""
		Reproject other rasters based on slope raster
		"""
		# reproject depth raster to slope resolution		
		# Resampling will use self.BASE_RESAMPLING_PATH if it exists
		group_raster, _, _ = self.resample(reference_raster=resampling_raster or slope_model.rasterfile.name, 
																raster_file=depth_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		# reproject drainage raster to slope resolution		
		# Do `resampling_raster or slope_model` so that it picks resampling_raster first if any as the reference raster
		drainage_raster, _, _ = self.resample(reference_raster=resampling_raster or slope_model.rasterfile.name, 
																raster_file=drainage_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		# reproject parentmaterial raster to slope resolution		
		# Do `resampling_raster or slope_model` so that it picks resampling_raster first if any as the reference raster
		parentmaterial_raster, _, _ = self.resample(reference_raster=resampling_raster or slope_model.rasterfile.name, 
																raster_file=parentmaterial_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		# reproject texture raster to slope resolution		
		# Do `resampling_raster or slope_model` so that it picks resampling_raster first if any as the reference raster
		texture_raster, _, _ = self.resample(reference_raster=resampling_raster or slope_model.rasterfile.name, 
																raster_file=texture_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		# reproject rockfragment raster to slope resolution		
		# Do `resampling_raster or slope_model` so that it picks resampling_raster first if any as the reference raster
		rockfragment_raster, _, _ = self.resample(reference_raster=resampling_raster or slope_model.rasterfile.name, 
																raster_file=rockfragment_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		# self.initialize_soil_slope_matrix()
		# slope_raster = self.normalize_rasters(slope_raster, self.slope_matrix, nodata)

		# self.initialize_soil_group_matrix()
		# group_raster = self.normalize_rasters(group_raster, self.soil_group_matrix, nodata)

		# self.initialize_soil_drainage_matrix()
		# drainage_raster = self.normalize_rasters(drainage_raster, self.soil_drainage_matrix, nodata)

		# self.initialize_soil_parent_material_matrix()
		# parentmaterial_raster = self.normalize_rasters(parentmaterial_raster, self.soil_parent_material_matrix, nodata)
		
		# self.initialize_soil_texture_matrix()
		# texture_raster = self.normalize_rasters(texture_raster, self.soil_texture_matrix, nodata)

		# self.initialize_soil_rock_fragment_matrix()
		# rockfragment_raster = self.normalize_rasters(rockfragment_raster, self.soil_rock_fragment_matrix, nodata)

		sqi = do_raster_operation(rasters=[slope_raster, group_raster, drainage_raster, parentmaterial_raster, texture_raster, rockfragment_raster],
								  operation=RasterOperationEnum.MULTIPLY, 
								  nodata=nodata)
		sqi = np.power(sqi, 1/6)
								
		self.initialize_sqi_matrix()
		
		df = pd.DataFrame({
						'ratio': sqi.filled(fill_value=nodata).flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in self.sqi_matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']
		
		datasource = df['mapping'].values.reshape(sqi.shape)
		datasource = datasource.astype(np.int32)
		
		# self.ratios = ratios # just for unit testing purposes
		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="sqi", 
			change_enum=SoilQualityIndexEnum, 
			metadata_raster_path=slope_raster_path,  
			nodata=nodata, 
			resolution=slope_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=MedalusSettings.SUB_DIR
		)		

	def calculate_management_quality_index(self, return_raster=False, resampling_raster=None):
		"""
		Compute Management Quality Index (MQI)
		MQI = [Population density x Land use intensity] ^ 1/2
		Args:
			return_raster (bool): If True, raw raster will be returned instead of computed statistics
		"""
		start_year, end_year, error = self.validate_periods()
		
		vector, error = self.get_vector()	
		if error:
			return self.return_with_error(error)

		pop_density_model, land_use_model, error = self.get_mqi_raster_models()
		if error:
			return self.return_with_error(error)

		# Extract Population Density raster meta data
		pop_density_meta = get_raster_meta(resampling_raster or pop_density_model.rasterfile.name)
		nodata = pop_density_meta['nodata']
		# Clip the raster
		# pop_density_meta_raster, nodata, pop_density_meta_raster_path = extract_pixels_using_vector(pop_density_model.rasterfile.name, vector, nodata)

		# Resampling will use self.BASE_RESAMPLING_PATH if it exists
		pop_density_meta_raster, _, pop_density_meta_raster_path = self.resample(reference_raster=resampling_raster, 
																raster_file=pop_density_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		# Extract Land use Intensity raster meta data
		land_use_meta = get_raster_meta(land_use_model.rasterfile.name)
		
		"""
		Reproject land use raster 
		"""
		# reproject soil raster to modis resolution
		
		# Do `resampling_raster or slope_model` so that it picks resampling_raster first if any as the reference raster
		land_use_meta_raster, _, land_use_meta_raster_path = self.resample(reference_raster=resampling_raster or pop_density_model.rasterfile.name, 
																raster_file=land_use_model.rasterfile.name, 
																vector=vector, nodata=nodata)
																
		ratios = do_raster_operation([pop_density_meta_raster, land_use_meta_raster], RasterOperationEnum.MULTIPLY, nodata)
		ratios = np.power(ratios, 1/2) # Raise to 1/2

		self.initialize_mqi_matrix()

		df = pd.DataFrame({
						'ratio': ratios.filled(fill_value=nodata).flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in self.mqi_matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high']) & (df['ratio'] != nodata)
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']

		datasource = df['mapping'].values.reshape(ratios.shape)
		datasource = datasource.astype(np.int32)
		
		self.ratios = ratios # just for unit testing purposes
		if return_raster:
			return datasource
		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="mqi", 
			change_enum=ManagementQualityIndexEnum, 
			metadata_raster_path=pop_density_meta_raster_path,  
			nodata=nodata, 
			resolution=pop_density_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=MedalusSettings.SUB_DIR
		)

	def calculate_vegetation_quality_index(self, resampling_raster=None):
		"""
		Calculate Vegetation Quality Index (SQI)
		VQI = POW((fire_risk * erosion * drought_resistance * vegetation_cover), 1/4)
		"""
		start_year, end_year, error = self.validate_periods()		
		vector, error = self.get_vector()	
		if error:
			return self.return_with_error(error)

		fire_risk_model, erosion_model, drought_model, plant_cover_model, error = self.get_vqi_raster_models()
		if error:
			return self.return_with_error(error)

		# Extract fire_risk raster meta data
		slope_meta = get_raster_meta(resampling_raster or fire_risk_model.rasterfile.name)
		nodata = slope_meta['nodata'] 
		# if nodata == float("nan"):
		# 	nodata = MedalusSettings.DEFAULT_NODATA
		
		# Resampling will use self.BASE_RESAMPLING_PATH if it exists
		fire_risk_raster, _, fire_risk_path = self.resample(reference_raster=resampling_raster, 
																raster_file=fire_risk_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		"""
		Reproject other rasters based on fire_risk raster
		"""
		# reproject erosion_protection raster to slope resolution
		
		# Do `resampling_raster or fire_risk_model` so that it picks resampling_raster first if any as the reference raster
		erosion_raster, _, erosion_path = self.resample(reference_raster=resampling_raster or fire_risk_model.rasterfile.name, 
															raster_file=erosion_model.rasterfile.name, 
															vector=vector, nodata=nodata)

		# reproject drought resistance raster to slope resolution
		# Do `resampling_raster or drought_model` so that it picks resampling_raster first if any as the reference raster
		drought_raster, _, drought_raster_path = self.resample(reference_raster=resampling_raster or fire_risk_model.rasterfile.name, 
																raster_file=drought_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		# reproject plant cover raster to slope resolution
		# Do `resampling_raster or drought_model` so that it picks resampling_raster first if any as the reference raster
		plant_cover_raster, _, plant_cover_raster_path = self.resample(reference_raster=resampling_raster or fire_risk_model.rasterfile.name, 
																raster_file=plant_cover_model.rasterfile.name, 
																vector=vector, nodata=nodata)

		# self.initialize_fire_risk_matrix()
		# fire_risk_raster = self.normalize_rasters(fire_risk_raster, self.fire_risk_matrix, nodata)

		# self.initialize_erosion_protection_matrix()
		# erosion_raster = self.normalize_rasters(erosion_raster, self.erosion_protection_matrix, nodata)

		# self.initialize_drought_resistance_matrix()
		# drought_raster = self.normalize_rasters(drought_raster, self.drought_resistance_matrix, nodata)

		# self.initialize_plant_cover_matrix()
		# plant_cover_raster = self.normalize_rasters(plant_cover_raster, self.plant_cover_matrix, nodata)
				
		vqi = do_raster_operation(rasters=[fire_risk_raster, erosion_raster, drought_raster, plant_cover_raster],
								operation=RasterOperationEnum.MULTIPLY, 
								nodata=nodata)
		# raise the vqi 
		vqi = np.power(vqi, 1/4)
								
		self.initialize_vqi_matrix()
		
		df = pd.DataFrame({
						'ratio': vqi.filled(fill_value=nodata).flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in self.vqi_matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']
		
		datasource = df['mapping'].values.reshape(vqi.shape)
		datasource = datasource.astype(np.int32)
		
		# self.ratios = ratios # just for unit testing purposes
		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="vqi", 
			change_enum=VegetationQualityEnum, 
			metadata_raster_path=fire_risk_path,  
			nodata=nodata, 
			resolution=fire_risk_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=MedalusSettings.SUB_DIR
		)	

	def calculate_esai(self):
		"""
		Compute ESAI
		Combines VQI, SQI, CQI and MQI indices
		"""		
		# Clip the raster and save for later referencing
		vector, error = self.get_vector()	
		start_model, error = self.get_raster_model(self.start_year, RasterCategoryEnum.ARIDITY_INDEX.value, throw_error=False)
		if error:
			return self.return_with_error(error)

		# meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)
		meta_raster_path = start_model.rasterfile.name		
		self.BASE_RESAMPLING_PATH = start_model.rasterfile.name # meta_raster_path

		start_meta = get_raster_meta(self.BASE_RESAMPLING_PATH)
		nodata = start_meta['nodata'] 

		self.error = None
		cqi = self.calculate_climate_quality_index(resampling_raster=self.BASE_RESAMPLING_PATH)
		if self.error:
			return self.return_with_error(self.error)

		sqi = self.calculate_soil_quality_index(resampling_raster=self.BASE_RESAMPLING_PATH)
		if self.error:
			return self.return_with_error(self.error)

		vqi = self.calculate_vegetation_quality_index(resampling_raster=self.BASE_RESAMPLING_PATH)
		if self.error:
			return self.return_with_error(self.error)

		mqi = self.calculate_management_quality_index(resampling_raster=self.BASE_RESAMPLING_PATH)
		if self.error:
			return self.return_with_error(self.error)

		base_file = cqi['rasterfile']
		cqi_raster = self.read_raster(cqi['rasterfile'], base_file)
		sqi_raster = self.read_raster(sqi['rasterfile'], base_file)
		mqi_raster = self.read_raster(mqi['rasterfile'], base_file)
		vqi_raster = self.read_raster(vqi['rasterfile'], base_file)

		# harmonize nodata values
		base_meta = get_raster_meta(self.get_file_path(base_file))
		nodata = base_meta.get('nodata')

		# replace with metadata 
 		
		rasters = reshape_rasters([cqi_raster, sqi_raster, mqi_raster, vqi_raster])
		esai = do_raster_operation(rasters=rasters,
								operation=RasterOperationEnum.MULTIPLY, 
								nodata=nodata)
		esai = np.power(esai, 1/4)

		self.initialize_esai_matrix()
		
		df = pd.DataFrame({
						'ratio': esai.filled(fill_value=nodata).flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in self.esai_matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']
		
		datasource = df['mapping'].values.reshape(esai.shape)
		datasource = datasource.astype(np.int32)
		
		# self.ratios = ratios # just for unit testing purposes
		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="esai", 
			change_enum=ESAIEnum, 
			metadata_raster_path=self.get_file_path(base_file), #meta_raster_path,  
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=MedalusSettings.SUB_DIR
		)	

	def get_file_path(self, url):
		return get_physical_file_path_from_url(self.request, url)

	def read_raster(self, file, ref_file):
		"""Read raster values while harmonizing the nodata values to ensure they are consistent

		Args:
			file (string): File path of the raster we want to read values from
			ref_file (string): File path of the raster whose nodata values we want to use
		"""
		values = get_raster_values(self.get_file_path(file), 
									band=GenericRasterBandEnum.HAS_SINGLE_BAND, 
									raster_source=self.raster_source, 
									windowed=False)	
		return harmonize_raster_nodata(values, self.get_file_path(file), self.get_file_path(ref_file))
		 
	def normalize_rasters(self, raster, matrix, nodata):
		"""
		Replace raster values with the matrix index values
		"""
		df = pd.DataFrame({
					'ratio': raster.flatten(),												
				})
		df['index'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in matrix:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['index']] = row['index']

		ds = df['index'].values.reshape(raster.shape)
		ds = ds.astype(float)
		return ds
	
	def initialize_aridity_matrix(self):
		self.aridity_matrix = [
			{#1
				'low': MIN_INT,
				'high': 50,
				'mapping': AridityIndexEnum.HYPER_ARID.key
			},
			{#2
				'low': 50,
				'high': 75,
				'mapping': AridityIndexEnum.ARID.key
			},
			{#3
				'low': 75,
				'high': 100,
				'mapping': AridityIndexEnum.SEMI_ARID.key
			},
			{#4
				'low': 100,
				'high': 125,
				'mapping': AridityIndexEnum.DRY_SUBHUMID.key
			},
			{#5
				'low': 125,
				'high': 150,
				'mapping': AridityIndexEnum.MOIST_SUBHUMID.key
			},
			{#6
				'low': 150,
				'high': MAX_INT,
				'mapping': AridityIndexEnum.HUMID.key
			}
		]

	def initialize_cqi_matrix(self):
		"""Initialize climate quality index matrix"""
		self.cqi_matrix = [
			{#1
				'low': MIN_INT,
				'high': 1.15,
				'mapping': ClimateQualityIndexEnum.HIGH_QUALITY.key
			},
			{#2
				'low': 1.15,
				'high': 1.81,
				'mapping': ClimateQualityIndexEnum.MODERATE_QUALITY.key
			},
			{#3
				'low': 1.81,
				'high': MAX_INT,
				'mapping': ClimateQualityIndexEnum.LOW_QUALITY.key
			},
		]

	def initialize_sqi_matrix(self):
		"""Initialize soil quality index matrix"""
		self.sqi_matrix = [
			{#1
				'low': MIN_INT,
				'high': 1.13,
				'mapping': SoilQualityIndexEnum.HIGH_QUALITY.key
			},
			{#2
				'low': 1.13,
				'high': 1.46,
				'mapping': SoilQualityIndexEnum.MODERATE_QUALITY.key
			},
			{#3
				'low': 1.46,
				'high': MAX_INT,
				'mapping': SoilQualityIndexEnum.LOW_QUALITY.key
			},
		]

	def initialize_mqi_matrix(self):
		"""Initialize Management Quality Index matrix"""
		self.mqi_matrix = [
			{#1
				'low': MIN_INT,
				'high': 1.25,
				'mapping': ManagementQualityIndexEnum.HIGH_QUALITY.key
			},
			{#2
				'low': 1.26,
				'high': 1.50,
				'mapping': ManagementQualityIndexEnum.MODERATE_QUALITY.key
			},
			{#3
				'low': 1.51,
				'high': MAX_INT,
				'mapping': ManagementQualityIndexEnum.LOW_QUALITY.key
			},
		]

	def initialize_vqi_matrix(self):
		"""Initialize vegetation quality index matrix"""
		self.vqi_matrix = [
			{#1
				'low': MIN_INT,
				'high': 1.13,
				'mapping': VegetationQualityEnum.HIGH_QUALITY.key
			},
			{#2
				'low': 1.13,
				'high': 1.38,
				'mapping': VegetationQualityEnum.MODERATE_QUALITY.key
			},
			{#3
				'low': 1.38,
				'high': MAX_INT,
				'mapping': VegetationQualityEnum.LOW_QUALITY.key
			},
		]

	def initialize_esai_matrix(self):
		"""
		Initialize ESAI matrix
		"""
		self.esai_matrix = [
			{#1
				'low': 0.999, # MIN_INT,
				'high': 1.17,
				'mapping': ESAIEnum.NONAFFECTED.key
			},
			{#2
				'low': 1.17,
				'high': 1.225,
				'mapping': ESAIEnum.POTENTIAL.key
			},
			{#3
				'low': 1.225,
				'high': 1.275,
				'mapping': ESAIEnum.FRAGILE_F1.key
			},
			{#4
				'low': 1.275,
				'high': 1.325,
				'mapping': ESAIEnum.FRAGILE_F2.key
			},
			{#5
				'low': 1.325,
				'high': 1.375,
				'mapping': ESAIEnum.FRAGILE_F3.key
			},
			{#6
				'low': 1.375,
				'high': 1.425,
				'mapping': ESAIEnum.CRITICAL_C1.key
			},
			{#7
				'low': 1.425,
				'high': 1.530,
				'mapping': ESAIEnum.CRITICAL_C2.key
			},
			{#8
				'low': 1.530,
				'high': 2.000, # MAX_INT,
				'mapping': ESAIEnum.CRITICAL_C3.key
			},
		]

	def initialize_rainfall_reclassification_matrix(self):
		self.rainfall_matrix = [
			{#1
				'low': MIN_INT,
				'high': 280,
				'mapping': 4
			},
			{#2
				'low': 280,
				'high': 650,
				'mapping': 2
			},
			{#3
				'low': 650,
				'high': MAX_INT,
				'mapping': 1
			}
		]

	def initialize_soil_slope_matrix(self):
		"""Initialize slope matrix"""
		self.slope_matrix = [
			{#1
				'low': MIN_INT,
				'high': 6,
				'mapping': SoilSlopeIndexEnum.VERY_GENTLE_TO_FLAT.key,
				'index':  SoilSlopeIndexEnum.VERY_GENTLE_TO_FLAT.index,
			},
			{#1
				'low': 6,
				'high': 18,
				'mapping': SoilSlopeIndexEnum.GENTLE.key,
				'index':  SoilSlopeIndexEnum.GENTLE.index,
			},
			{#1
				'low': 18,
				'high': 35,
				'mapping': SoilSlopeIndexEnum.STEEP.key,
				'index':  SoilSlopeIndexEnum.STEEP.index,
			},
			{#1
				'low': 35,
				'high': MAX_INT,
				'mapping': SoilSlopeIndexEnum.VERY_STEEP.key,
				'index':  SoilSlopeIndexEnum.VERY_STEEP.index,
			},
		]
	
	def initialize_soil_group_matrix(self):
		"""Initialize soil depth matrix"""
		self.soil_group_matrix = [
			{#1
				'low': MIN_INT,
				'high': 15,
				'mapping': SoilGroupIndexEnum.VERY_SHALLOW.key,
				'index': SoilGroupIndexEnum.VERY_SHALLOW.index,
			},
			{#2
				'low': 15,
				'high': 30,
				'mapping': SoilGroupIndexEnum.SHALLOW.key,
				'index': SoilGroupIndexEnum.SHALLOW.index,
			},
			{#3
				'low': 30,
				'high': 75,
				'mapping': SoilGroupIndexEnum.MODERATE.key,
				'index': SoilGroupIndexEnum.MODERATE.index,
			},
			{#4
				'low': 35,
				'high': MAX_INT,
				'mapping': SoilGroupIndexEnum.DEEP.key,
				'index': SoilGroupIndexEnum.DEEP.index,
			},
		]

	def initialize_soil_drainage_matrix(self):
		"""Initialize soil drainage matrix"""
		self.soil_drainage_matrix = [
			{#1
				'low': MIN_INT,
				'high': 15,
				'mapping': SoilDrainageIndexEnum.WELL_DRAINED.key,
				'index': SoilDrainageIndexEnum.WELL_DRAINED.index,
			},
			{#2
				'low': 15,
				'high': 30,
				'mapping': SoilDrainageIndexEnum.IMPERFECTLY_DRAINED.key,
				'index': SoilDrainageIndexEnum.IMPERFECTLY_DRAINED.index,
			},
			{#3
				'low': 30,
				'high': 75,
				'mapping': SoilDrainageIndexEnum.POORLY_DRAINED.key,
				'index': SoilDrainageIndexEnum.POORLY_DRAINED.index,
			},
		]

	def initialize_soil_parent_material_matrix(self):
		"""Initialize soil parent material matrix"""
		self.soil_parent_material_matrix = [
			{#1
				'low': MIN_INT,
				'high': 15,
				'mapping': SoilParentMaterialEnum.GOOD.key,
				'index': SoilParentMaterialEnum.GOOD.index,
			},
			{#2
				'low': 15,
				'high': 30,
				'mapping': SoilParentMaterialEnum.MODERATE.key,
				'index': SoilParentMaterialEnum.MODERATE.index,
			},
			{#3
				'low': 30,
				'high': 75,
				'mapping': SoilParentMaterialEnum.POOR.key,
				'index': SoilParentMaterialEnum.POOR.index,
			},
		]

	def initialize_soil_texture_matrix(self):
		"""Initialize soil texture matrix"""
		self.soil_texture_matrix = [
			{#1
				'low': MIN_INT,
				'high': 15,
				'mapping': SoilTextureEnum.GOOD.key,
				'index': SoilTextureEnum.GOOD.index,
			},
			{#2
				'low': 15,
				'high': 30,
				'mapping': SoilTextureEnum.MODERATE.key,
				'index': SoilTextureEnum.MODERATE.index,
			},
			{#3
				'low': 30,
				'high': 75,
				'mapping': SoilTextureEnum.POOR.key,
				'index': SoilTextureEnum.POOR.index,
			},
			{#4
				'low': 75,
				'high': MAX_INT,
				'mapping': SoilTextureEnum.VERY_POOR.key,
				'index': SoilTextureEnum.VERY_POOR.index,
			},
		]

	def initialize_soil_rock_fragment_matrix(self):
		"""Initialize soil rock fragments matrix"""
		self.soil_rock_fragment_matrix = [
			{#1
				'low': MIN_INT,
				'high': 20,
				'mapping': SoilRockFragmentEnum.BARE_TO_SLIGHTLY_STONY.key,
				'index': SoilRockFragmentEnum.BARE_TO_SLIGHTLY_STONY.index,
			},
			{#2
				'low': 20,
				'high': 60,
				'mapping': SoilRockFragmentEnum.STONY.key,
				'index': SoilRockFragmentEnum.STONY.index,
			},
			{#3
				'low': 60,
				'high': MAX_INT,
				'mapping': SoilRockFragmentEnum.VERY_STONY.key,
				'index': SoilRockFragmentEnum.VERY_STONY.index,
			},
		]

	def initialize_plant_cover_matrix(self):
		"""Initialize plant cover matrix"""
		self.plant_cover_matrix = [
			{#1
				'low': MIN_INT,
				'high': 10,
				'mapping': PlantCoverEnum.VERY_LOW.key,
				'index': PlantCoverEnum.VERY_LOW.index,
			},
			{#2
				'low': 10,
				'high': 40,
				'mapping': PlantCoverEnum.LOW.key,
				'index': PlantCoverEnum.LOW.index,
			},
			{#3
				'low': 40,
				'high': MAX_INT,
				'mapping': PlantCoverEnum.HIGH.key,
				'index': PlantCoverEnum.HIGH.index,
			},
		]

	# def initialize_fire_risk_matrix(self):
	# 	"""Initialize fire risk matrix"""
	# 	self.fire_risk_matrix = [
	# 		{#1
	# 			'mapping': FireRiskEnum.LOW.key,
	# 			'index': FireRiskEnum.LOW.index,
	# 		},
	# 		{#2
	# 			'mapping': FireRiskEnum.MODERATE.key,
	# 			'index': FireRiskEnum.MODERATE.index,
	# 		},
	# 		{#3				
	# 			'mapping': FireRiskEnum.HIGH.key,
	# 			'index': FireRiskEnum.HIGH.index,
	# 		},
	# 		{#4
	# 			'mapping': FireRiskEnum.VERY_HIGH.key,
	# 			'index': FireRiskEnum.VERY_HIGH.index,
	# 		},
	# 	]
	
	def get_ai_raster_models(self):
		"""
		Aridity Index:
		Get the MAP and MAE models associated with start period
		"""
		rain_model, rain_error = self.get_raster_model(self.start_year, RasterCategoryEnum.RAINFALL.value, throw_error=False)
		mae_model, mae_error = self.get_raster_model(self.start_year, RasterCategoryEnum.EVAPOTRANSPIRATION.value, throw_error=False)
		# mae_model, mae_error = self.get_raster_model(self.start_year, RasterCategoryEnum.LULC.value, throw_error=False)
		return (rain_model, mae_model, rain_error or mae_error)

	def get_cqi_raster_models(self, include_aspect=True):
		"""
		Climate Quality Index:
		Get the Rainfall and Aspect models associated with start period
		"""
		rain_model, rain_error = self.get_raster_model(self.start_year, RasterCategoryEnum.RAINFALL.value, throw_error=False)
		aridity_model, aridity_error = self.get_raster_model(self.start_year, RasterCategoryEnum.ARIDITY_INDEX.value, throw_error=False)
		if include_aspect:
			aspect_model, aspect_error = self.get_raster_model(self.start_year, RasterCategoryEnum.ASPECT.value, throw_error=False)
			return (aridity_model, rain_model, aspect_model, aridity_error or rain_error or aspect_error)
		else:
			return (aridity_model, rain_model, aridity_error or rain_error)

	def get_mqi_raster_models(self):
		"""
		Managenent Quality Index:
		Get the Population Density and Land Use Intensity models associated with start period
		"""
		pop_model, pop_error = self.get_raster_model(self.start_year, RasterCategoryEnum.POPULATION_DENSITY.value, throw_error=False)
		land_model, land_error = self.get_raster_model(self.start_year, RasterCategoryEnum.LAND_USE_DENSITY.value, throw_error=False)
		return (pop_model, land_model, pop_error or land_error)
	
	def get_sqi_raster_models(self):
		"""
		Soil Quality Index:
		Get Slope, Soil Depth, Drainage, Parent Material, Texture, Rock Fragments models associated with start period
		"""
		slope_model, slope_error = self.get_raster_model(self.start_year, RasterCategoryEnum.SOIL_SLOPE.value, throw_error=False)
		depth_model, depth_error = self.get_raster_model(self.start_year, RasterCategoryEnum.SOIL_GROUP.value, throw_error=False)
		drainage_model, drainage_error = self.get_raster_model(self.start_year, RasterCategoryEnum.SOIL_DRAINAGE.value, throw_error=False)
		parent_model, parent_error = self.get_raster_model(self.start_year, RasterCategoryEnum.SOIL_PARENT_MATERIAL.value, throw_error=False)
		texture_model, texture_error = self.get_raster_model(self.start_year, RasterCategoryEnum.SOIL_TEXTURE.value, throw_error=False)
		fragment_model, fragment_error = self.get_raster_model(self.start_year, RasterCategoryEnum.SOIL_ROCK_FRAGMENT.value, throw_error=False)
		return (slope_model, depth_model, drainage_model, parent_model, texture_model, fragment_model, slope_error or depth_error or drainage_error or parent_error or texture_error or fragment_error)

	def get_vqi_raster_models(self):
		"""
		Get Fire Risk, Erosion Protection, Drought Resistance, Plant Cover models associated with start period
		"""
		fire_model, fire_error = self.get_raster_model(self.start_year, RasterCategoryEnum.FIRE_RISK.value, throw_error=False)
		erosion_model, erosion_error = self.get_raster_model(self.start_year, RasterCategoryEnum.EROSION_PROTECTION.value, throw_error=False)
		drought_model, drought_error = self.get_raster_model(self.start_year, RasterCategoryEnum.DROUGHT_RESISTANCE.value, throw_error=False)
		plant_model, plant_error = self.get_raster_model(self.start_year, RasterCategoryEnum.PLANT_COVER.value, throw_error=False)
		return (fire_model, erosion_model, drought_model, plant_model, fire_error or erosion_error or drought_error or plant_error)

	def get_raster_model(self, year, raster_category, throw_error=True):
		"""
		Get the MAP or MAE models associated with start and end period

		Returns:
			tuple (model, error)
		"""
		model = get_raster_models(raster_year=year, 
								# raster_source=self.raster_source.value,
								raster_category=raster_category, 
								admin_zero_id=self.admin_0
							).first()
		error = None
		if not model:
			error = _("Year {0} does not have an associated {1} {2} raster{3}.".format(year, raster_category,
						"", #self.raster_source.value, 
						" for the selected country" if self.admin_0 else ""))
			if throw_error:
				raise ModelNotExistError(error)
		return (model, error)
		
	def get_vector(self):
		return get_vector(admin_level=self.admin_level, 
						  shapefile_id=self.shapefile_id, 
						  custom_vector_coords=self.custom_vector_coords, 
						  admin_0=self.admin_0,
						  request=self.request)

	def return_with_error(self, error):		
		self.error = error
		return return_with_error(self.request, error)
