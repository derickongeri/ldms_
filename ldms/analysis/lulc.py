from django.utils.translation import gettext as _
from ldms.utils.raster_util import RasterCalcHelper
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry

import json
from ldms.models import RegionalAdminLevel, AdminLevelZero, AdminLevelOne, AdminLevelTwo
import datetime
from rest_framework.response import Response
from ldms.utils.common_util import cint, return_with_error, validate_years
from ldms.utils.file_util import (get_absolute_media_path, get_download_url, 
								get_media_dir, file_exists)
from ldms.utils.raster_util import (get_raster_values, get_raster_object, 
								save_raster, get_raster_meta, reproject_raster,
								extract_pixels_using_vector, clip_raster_to_vector,
								return_raster_with_stats, get_raster_models)
from ldms.utils.vector_util import get_vector
import numpy as np
import pandas as pd
import enum
import rasterio
from rasterio.warp import Resampling
from ldms.enums import (LulcCalcEnum, LulcChangeEnum, LCEnum, GenericRasterBandEnum,
	 RasterSourceEnum, RasterCategoryEnum)

class LuLcSettings:
	SUB_DIR = "" # "lulc" # Subdirectory to store rasters for lulc

class LULC:
	"""
	Wrapper class for calculating LULC
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
			**raster_type (int)**:  
				The type of raster files to be used
			**start_year (int)**: 
				Starting year for which raster files should be used. 
			**end_year (int)**: 
				End year for which raster files should be used. 
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
		self.transform = kwargs.get('transform', "area")
		self.request = kwargs.get('request', None)
		self.error = None
		self.analysis_type = None #one of LULC or LULC_CHANGE
		self.raster_source = RasterSourceEnum.LULC # kwargs.get('raster_source', RasterSourceEnum.LULC)
		self.enforce_single_year = kwargs.get('enforce_single_year', True)
		self.admin_0 = kwargs.get('admin_0', None)

		# #matrix to define land change type. The dict key is the base value
		self.transition_matrix = {
			LCEnum.FOREST.value: { "stable": [LCEnum.FOREST.value, LCEnum.WATER.value], 
					"improved": [], 
					"degraded": [LCEnum.GRASSLAND.value, LCEnum.CROPLAND.value, LCEnum.WETLAND.value,
								LCEnum.ARTIFICIAL.value, LCEnum.BARELAND.value]
					},
			LCEnum.GRASSLAND.value: { "stable": [LCEnum.GRASSLAND.value, LCEnum.WATER.value], 
					"improved": [LCEnum.FOREST.value, LCEnum.CROPLAND.value], 
					"degraded": [LCEnum.WETLAND.value, LCEnum.ARTIFICIAL.value, LCEnum.BARELAND.value]
					},
			LCEnum.CROPLAND.value: { "stable": [LCEnum.CROPLAND.value, LCEnum.WATER.value], 
						"improved": [LCEnum.FOREST.value], 
						"degraded": [LCEnum.GRASSLAND.value, LCEnum.WETLAND.value, 
									LCEnum.ARTIFICIAL.value, LCEnum.BARELAND.value]
					},
			LCEnum.WETLAND.value: { "stable": [LCEnum.WETLAND.value, LCEnum.WATER.value], 
					"improved": [], 
					"degraded": [LCEnum.FOREST.value, LCEnum.GRASSLAND.value, 
									LCEnum.CROPLAND.value, LCEnum.ARTIFICIAL.value, LCEnum.BARELAND.value]
					},
			LCEnum.ARTIFICIAL.value: { "stable": [LCEnum.ARTIFICIAL.value, LCEnum.WATER.value], 
					"improved": [LCEnum.FOREST.value, LCEnum.GRASSLAND.value, LCEnum.CROPLAND.value, 
								LCEnum.WETLAND.value, LCEnum.BARELAND.value], 
					"degraded": []
					},
			LCEnum.BARELAND.value: { "stable": [LCEnum.BARELAND.value, LCEnum.WATER.value], 
					"improved": [LCEnum.FOREST.value, LCEnum.GRASSLAND.value, LCEnum.CROPLAND.value, 
								LCEnum.WETLAND.value], 
					"degraded": [LCEnum.ARTIFICIAL.value]
					},
			LCEnum.WATER.value: { "stable": [LCEnum.FOREST.value, LCEnum.GRASSLAND.value, 
									  LCEnum.CROPLAND.value, LCEnum.WETLAND.value, 
									  LCEnum.ARTIFICIAL.value, LCEnum.BARELAND.value, 
									  LCEnum.WATER.value], 
					"improved": [], 
					"degraded": []
					},
		} 

	def return_with_error(self, error):		
		self.error = error
		return return_with_error(self.request, error)
	
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
							both_valid=self.analysis_type == LulcCalcEnum.LULC_CHANGE)

	def get_vector(self):
		return get_vector(admin_level=self.admin_level, 
						  shapefile_id=self.shapefile_id, 
						  custom_vector_coords=self.custom_vector_coords, 
						  admin_0=None,
						  request=self.request
						)

	def calculate_lulc(self):
		"""
		Compute Land Use Land Cover
		
		Returns:
			[Response]: [A JSON string with statistic values]
		"""    
		self.analysis_type = LulcCalcEnum.LULC    
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
		raster_type = cint(raster_type)
		if not raster_type:
			return self.return_with_error(_("No raster type has been selected"))

		"""
		Validate analysis periods
		"""
		start_year, end_year, period_error = self.validate_periods()
		if period_error:
			return self.return_with_error(period_error)

		if self.enforce_single_year:
			if start_year != end_year:
				return self.return_with_error(_("LULC can only be analysed for a single period"))

		# Get Raster Models	by period and raster type
		raster_models = get_raster_models(admin_zero_id=self.admin_0,
						raster_category=RasterCategoryEnum.LULC.value,
						raster_source=self.raster_source.value,
						raster_year__gte=start_year, 
						raster_year__lte=end_year)

		if not raster_models:
			return self.return_with_error(_("No matching rasters"))

		if self.enforce_single_year:
			if len(raster_models) > 1:
				return self.return_with_error(_("Multiple LULC rasters exist for the selected period"))

		for raster_model in raster_models:			
			# for raster_model in raster_models:
			raster_path = get_media_dir() + raster_model.rasterfile.name

			# Validate existence of the raster file
			if not file_exists(raster_path):
				return self.return_with_error(_("Raster %s does not exist" % (raster_model.rasterfile.name)))

			if raster_model.raster_year == start_year:
				lulc_raster, lulc_raster_path, nodata = clip_raster_to_vector(raster_model.rasterfile.name, vector)
			
		hlper = RasterCalcHelper(vector=vector,
					rasters=raster_models,
					raster_type_id=raster_type,
					stats=[],
					is_categorical=True,
					transform=transform)
		res = hlper.get_stats()
		# return res
		return return_raster_with_stats(
			request=self.request,
			datasource=lulc_raster[0], # since its a (1, width, height) matrix
			prefix="lulc", 
			change_enum=LulcChangeEnum, 
			metadata_raster_path=lulc_raster_path, 
			nodata=nodata, 
			resolution=raster_model.resolution,
			start_year=start_year,
			end_year=end_year,
			subdir=LuLcSettings.SUB_DIR,
			results=res
		)

	def calculate_lulc_change(self, return_no_map=False):
		"""
		Compute Land Use Land Cover Change between two rasters

		Args:
			return_no_map (bool): Determines if mapping will be done or
			only a Pandas dataframe will be returned with column indicies
			`start` and `end`.		
		Returns:
			[Response]: [A JSON string with statistic values]		
		# TODO: Validate the rasters are similar
		"""

		def generate_array(size=(10, 30)):
			return np.random.randint(1, 8, size=size)

		self.analysis_type = LulcCalcEnum.LULC_CHANGE

		# #matrix to define land change type. The dict key is the base value
		transition_matrix = self.transition_matrix 
		
		"""
		Validate analysis periods
		"""
		start_year, end_year, period_error = self.validate_periods()
		if period_error:
			return self.return_with_error(period_error)

		# Get rasters
		start_model = get_raster_models(
						admin_zero_id=self.admin_0,
						raster_category=RasterCategoryEnum.LULC.value,	
						raster_source=self.raster_source.value,					
						raster_year=start_year).first()

		end_model = get_raster_models(
						admin_zero_id=self.admin_0,
						raster_category=RasterCategoryEnum.LULC.value,
						raster_source=self.raster_source.value,
						raster_year=end_year).first()
		if not start_model:
			return self.return_with_error(_("No LULC raster is associated with period %s" % (start_year)))
		if not end_model:
			return self.return_with_error(_("No LULC raster is associated with period %s" % (end_year)))
		
		vector, error = self.get_vector()
		if error:
			return self.return_with_error(error)

		# Read the values of the rasters
		meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)
		start_arry, nodata, start_rastfile = extract_pixels_using_vector(start_model.rasterfile.name, 
										vector, use_temp_dir=False)

		# Reproject based on the start model
		end_raster_file, nodata = reproject_raster(reference_raster=start_model.rasterfile.name, 
										   raster=end_model.rasterfile.name,
										   resampling=Resampling.average)

		end_arry, nodata, end_rastfile = extract_pixels_using_vector(end_raster_file, 
										vector, use_temp_dir=False)
		
		meta = get_raster_meta(start_model.rasterfile.name)
		df = pd.DataFrame({'base': start_arry.flatten(), 'target': end_arry.flatten()})

		# fill nan with nodata values
		df['change'] = np.full(df['base'].shape, meta['nodata'])

		if return_no_map == True:
			return df

		for key in transition_matrix.keys():
			"""
			get where the 'start' is equal to the dict key
			df['base'] contains pixel values for the base period
			df['target'] contains pixel values for the target period
			"""
			stable = transition_matrix[key]['stable']
			improved = transition_matrix[key]['improved']
			degraded = transition_matrix[key]['degraded']
			if stable:
				df.loc[(df['base']==key) & (df['target'].isin(stable)), ['change']] = LulcChangeEnum.STABLE.key # stable
			if improved:
				df.loc[(df['base']==key) & (df['target'].isin(improved)), ['change']] = LulcChangeEnum.IMPROVED.key # improved
			if degraded:
				df.loc[(df['base']==key) & (df['target'].isin(degraded)), ['change']] = LulcChangeEnum.DEGRADED.key # degraded
					
		# convert to old shape
		dataset = df['change'].values.reshape(start_arry.shape)

		return return_raster_with_stats(
			request=self.request,
			datasource=dataset, 
			prefix="lulcchange", 
			change_enum=LulcChangeEnum, 
			metadata_raster_path=meta_raster_path, 
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=LuLcSettings.SUB_DIR,
			extras={'rasters': {
								start_model.raster_year: get_download_url(self.request, start_rastfile.split("/")[-1]), 
								end_model.raster_year: get_download_url(self.request, end_rastfile.split("/")[-1])
							}
						}
		)
		
	def get_comparative_rasters(self):
		"""
		Returns a Pandas Dataframe of the values of two comparing 
		periods with indices `start` and `end`
		"""
		pass
