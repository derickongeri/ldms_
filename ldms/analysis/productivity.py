import rasterio
import numpy as np
import numpy.ma as ma
import pandas as pd
import enum
import math
from django.utils.translation import gettext as _
from rest_framework.response import Response
from ldms.analysis.vegetation_index import VegetationIndex
from ldms.utils.raster_util import (get_raster_values, save_raster, reproject_raster, 
					do_raster_operation, get_raster_models)
from ldms.enums import (RasterOperationEnum, RasterCategoryEnum, GenericRasterBandEnum, 
			RasterSourceEnum, TrajectoryChangeTernaryEnum, StateChangeTernaryEnum,
			PerformanceChangeBinaryEnum, ProductivityChangeTernaryEnum,
			StateChangeQuinaryEnum, StateChangeBinaryEnum,
			TrajectoryChangeQuinaryEnum, TrajectoryChangeBinaryEnum,
			ProductivityChangeBinaryEnum
			)
from ldms.utils.common_util import return_with_error, get_random_floats, cint, validate_years
from ldms.utils.file_util import (generate_file_name, get_absolute_media_path, get_download_url, 
								file_exists, get_physical_file_path_from_url)
from sklearn.linear_model import LinearRegression
from scipy import stats
import tempfile 
from ldms.utils.raster_util import (extract_pixels_using_vector, get_raster_meta, clip_raster_to_vector, reshape_rasters,
				return_raster_with_stats)
from ldms.utils.vector_util import get_vector
from scipy.stats import percentileofscore
from ldms import ModelNotExistError, AnalysisParamError
import collections 
from rasterio.warp import Resampling
from django.conf import settings
import copy

MIN_INT = settings.MIN_INT # -9223372036854775807
MAX_INT = settings.MAX_INT # 9223372036854775807 

THREE_CLASS_MAP = 3
FIVE_CLASS_MAP = 5

class ProductivitySettings:
	PVALUE_CUTOFF = 0.05 # p value to be considered significant
	DIVISION_FACTOR = 0.00001 # NDVI Values are stored after multiply them by 10000
	TOTAL_PERCENTILES = 10 # no of classes to classify state into
	STATE_CHANGE_POSITIVE_CUTOFF = 2 # +ve cutoff for improved state
	STATE_CHANGE_NEGATIVE_CUTOFF = -2 # -ve cutoff for degraded state
	BASELINE_START = 2000 # start of the baseline
	BASELINE_END = 2015 # end of the baseline
	MIN_COMPARISON_RANGE = 3 # minimum number of periods to perform state comparison
	PERC_FREQ_ADJUSTMENT = 5 # percentage value to adjust the frequency distributions by
	# DEFAULT_NODATA = 255 # default value of nodata
	MIN_RASTERS_FOR_STATE = 10 # min rasters that are needed to compute state
	ENFORCE_MIN_RASTERS_FOR_STATE = False 
	USE_RUE_FOR_TRAJECTORY = False #use RUE to compute trajectory

	PERFORMANCE_BASE_SOIL_RASTER = "SoilGrids.tif"
	PERFORMANCE_BASE_LC_RASTER = "LC_2008.tif"# "2000.tif"
	PERFORMANCE_DEGRADED_CUTOFF = 0.5 # value to determine if perfomance is degraded else its stable

	SUB_DIR = "" # "prod" # Subdirectory to store rasters for productivity analysis

	MIN_RASTERS_FOR_TRAJECTORY = 8 # min rasters that are needed to compute trajectory

	# version 2
	MIN_RASTERS_FOR_STATE_V2 = 16 # min rasters that are needed to compute state version 2
	MIN_RASTERS_FOR_TRAJECTORY_V2 = 16 # min rasters that are needed to compute trajectory version 2
	MIN_RASTERS_FOR_PERFORMANCE_V2 = 16 # min rasters that are needed to compute performance version 2
	ENFORCE_MIN_RASTERS_FOR_PERFORMANCE = True
	DEFAULT_BASELINE_END_YEAR = 2015 # default baseline end year when computing main productivity indicator
 
class Productivity:
	"""
	Wrapper class for Different productivity sub-indicators.
	State and performance depend only on NDVI/SAVI/MSAVI data. Trajectory
	needs to also account for climate data
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
			veg_index (RasterCategoryEnum):
				Vegetation Index to use. One of NDVI, MSAVI or SAVI
			baseline_year (int):
				The baseline selected when computing main indicator in the updated SDG 15.3.1 
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
		self.reference_eco_units = kwargs.get('reference_eco_units', None)
		self.raster_source = kwargs.get('raster_source', RasterSourceEnum.MODIS)
		self.admin_0 = kwargs.get('admin_0', None)
		self.veg_index = kwargs.get('veg_index', RasterCategoryEnum.NDVI.value)
		self.compute_version = kwargs.get('version', 1) #Are we computed updated indicators
		self.class_map = kwargs.get('class_map', THREE_CLASS_MAP) #class-map for state to use

		self.settings = ProductivitySettings()

		# If we are computing sub-indicator or the main Productivity indicator
		self.in_sub_indicator_context = True
		self.baseline_end_year = kwargs.get('baseline_end_year', ProductivitySettings.DEFAULT_BASELINE_END_YEAR) #class-map for state to use
		
	def validate_periods(self, both_valid=True):
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

	def get_vi_raster_model(self, year, throw_error=True):
		"""
		Get the NDVI/SAVI/MSAVI models associated with start and end period
		"""
		model = get_raster_models(raster_year=year, 
								raster_source=self.raster_source.value,
								raster_category=self.veg_index, 
								admin_zero_id=self.admin_0
							).first()
		error = None
		if not model:
			error = _("Year {0} does not have an associated {1} {2} raster{3}.".format(year, self.veg_index,
						self.raster_source.value, " for the selected country" if self.admin_0 else ""))
			if throw_error:
				raise ModelNotExistError(error)
		return (model, error)
	
	def get_rainfall_raster_model(self, year, throw_error=True):
		"""
		Get the models associated with start and end period
		"""
		start_model = get_raster_models(raster_year=year, 
								raster_source=self.raster_source.value,
								raster_category=RasterCategoryEnum.RAINFALL.value
							).first()	
		error = None
		if not start_model:
			error = _("Year {} does not have an associated raster for {}".format(year, RasterCategoryEnum.RAINFALL.value))
			if throw_error:
				raise ModelNotExistError(error)
		return (start_model, error)

	def get_start_and_end_ndvi_raster_models(self, both_valid=True):
		"""
		Get the models associated with start and end period
		"""
		start_model, start_error = self.get_vi_raster_model(self.start_year, throw_error=False)
		end_model, end_error = None, None
		if both_valid:
			end_model, end_error = self.get_vi_raster_model(self.end_year, throw_error=False)
		return (start_model, end_model, start_error or end_error)

	def get_vi_raster_models(self, start_year, end_year):
		"""
		Get the NDVI/MSAVI/SAVI models associated with start and end period
		"""
		return get_raster_models(raster_year__gte=start_year, 
									raster_year__lte=end_year,
									raster_source=self.raster_source.value,
									raster_category=self.veg_index, 
									admin_zero_id=self.admin_0)

	def prevalidate(self, both_valid=True):
		"""
		Do common prevalidations and processing

		Returns:
			A tuple	(error, vector, start_model, end_model, start_year, end_year)
		"""
		start_year, end_year, error = self.validate_periods(both_valid=both_valid)
		vector, error = self.get_vector()	
		start_model, end_model, base_raster, target_raster = None, None, None, None
		if not error:
			start_model, end_model, error = self.get_start_and_end_ndvi_raster_models(both_valid=both_valid)

		return (error, vector, start_model, end_model, start_year,  end_year)

	def get_vector(self):
		return get_vector(admin_level=self.admin_level, 
						  shapefile_id=self.shapefile_id, 
						  custom_vector_coords=self.custom_vector_coords, 
						  admin_0=self.admin_0,
						  request=self.request)

	def calculate_trajectory(self):
		"""
		Calculate Trajectory sub-indicator. Trajectory measures the rate of change in 
		primary productivity over time.
		"""
		if self.compute_version == 2:
			if self.in_sub_indicator_context:
				return self._calculate_trajectory_version2(start_year=self.start_year,
							end_year=self.end_year)
			else: # we are computing the main indicator where baseline is involved
				# get the state for the baseline period
				baseline_start_year = (self.baseline_end_year - ProductivitySettings.MIN_RASTERS_FOR_TRAJECTORY_V2) + 1
				reporting_period_start_year = (self.end_year - ProductivitySettings.MIN_COMPARISON_RANGE) + 1
				original_end_year = copy.copy(self.end_year)

				baseline = self._calculate_trajectory_version2(start_year=baseline_start_year,
							end_year=self.baseline_end_year, return_raw=True, is_baseline=True)
				if self.error:
					return self.return_with_error(self.error)

				self.end_year = original_end_year
				# get state for reporting period
				reporting = self._calculate_trajectory_version2(start_year=reporting_period_start_year,
							end_year=self.end_year, return_raw=True, is_baseline=False)
				if self.error:
					return self.return_with_error(self.error)

				change_matrix = self.initialize_trajectory_change_matrix()

				df = pd.DataFrame({
								'baseline': baseline['datasource'].flatten(),
								'reporting': reporting['datasource'].flatten(),
							})
				df['mapping'] = reporting['nodata']

				# Replace values
				for row in change_matrix:
					# filter all matching entries as per the matrix
					mask = (df['baseline'] == row['base']) & (df['reporting'] == row['curr'])
					df.loc[mask, ['mapping']] = row['mapping']
				
				datasource = df['mapping'].values.reshape(baseline['datasource'].shape)
				datasource = datasource.astype(np.int32)

				return return_raster_with_stats(
					request=self.request,
					datasource=datasource, 
					prefix="traj", 
					change_enum=TrajectoryChangeBinaryEnum,
					metadata_raster_path=reporting['meta_path'],
					nodata=reporting['nodata'], 
					resolution=reporting['resolution'],
					start_year=baseline_start_year,
					end_year=self.end_year,
					subdir=ProductivitySettings.SUB_DIR 
				)
		return self._calculate_trajectory_version1()

	def _calculate_trajectory_version1(self):
		"""
		Calculate Trajectory sub-indicator. Trajectory measures the rate of change in 
		primary productivity over time.
		
		Steps:
		1. Compute pixel level regression values. We only interested in the slope
		2. For each pixel, perform a Mann-Kendall significance test on the pixel values
		3. For those that pass the significance test, perform a transitional mapping 
		   to determine if degraded, stable or improved.
		4. Generate a raster containing the transitional values
		5. compute the raster statistics to be returned together with the raster
		"""
		def get_linear_regression(item):
			"""Get the slope"""
			# slope, intercept, r_value, p_value, std_err = stats.linregress(time_array, item['values'])
			data = extract_period_values(item)
			if data == nodata:
				return nodata		
			
			slope, intercept, r_value, p_value, std_err = stats.linregress(time_array, data)
			return slope

		def extract_period_values(item):
			data = []			
			# Extract values for all the periods to form the data series
			for i, tm in enumerate(time_array):
				val = item[str(tm)]
				if val == nodata: # if any value has nodata, then return nodata as val of slope
					return nodata
				data.append(val)
			return data

		def get_pvalue(item):
			"""Get pvalue"""
			data = extract_period_values(item)
			if data == nodata:
				return nodata	
			tau, p_value = stats.kendalltau(time_array, data)
			# tau, p_value = stats.kendalltau(time_array, [item['base'], item['target']])
			# p_value = p_value if not np.isnan(p_value) else 1.
			return p_value

		
		error, vector, start_model, end_model, start_year, end_year = self.prevalidate()
		if error:
			return self.return_with_error(error)

		ndvi_models = self.get_vi_raster_models(self.start_year, self.end_year)
		if not ndvi_models:
			return self.return_with_error(_("There are no {0} rasters for the selected periods".format(self.veg_index)))

		if len(ndvi_models) < ProductivitySettings.MIN_RASTERS_FOR_TRAJECTORY:
			return self.return_with_error(_("A minimum of %s years of %s data is needed to compute trajectory" % (ProductivitySettings.MIN_RASTERS_FOR_TRAJECTORY, self.raster_source.value)))

		start_model, end_model, error = self.get_start_and_end_ndvi_raster_models()
		if error:
			return self.return_with_error(error)
		
		# Extract raster meta data
		meta = get_raster_meta(start_model.rasterfile.name)
		nodata = meta['nodata']
		
		"""
		Extract pixels of the vector we are interested in.
		We ignore the rest of the raster
		"""
		ndvi_rasters = self.get_vi_rasters(self.start_year, self.end_year)

		# base_raster, nodata = extract_pixels_using_vector(start_model.rasterfile.name, vector, nodata)
		# target_raster, nodata = extract_pixels_using_vector(end_model.rasterfile.name, vector, nodata)

		if ProductivitySettings.USE_RUE_FOR_TRAJECTORY:
			# If we are using RUE, we compute NDIV/Rainfall and then use the result as
			# the input rasters.
			# if using RUE, use rainfall raster instead of computing slope
			# we divide NDVI by Rainfall to get RUE
			start_model_rainfall, error = self.get_rainfall_raster_model(self.start_year, throw_error=False)
			if error:
				return self.return_with_error(error)
			end_model_rainfall, error = self.get_rainfall_raster_model(self.end_year, throw_error=False)
			if error:
				return self.return_with_error(error)

			base_raster_rainfall, nodata, rastfile = extract_pixels_using_vector(start_model_rainfall.rasterfile.name, vector)
			target_raster_rainfall, nodata, rastfile = extract_pixels_using_vector(end_model_rainfall.rasterfile.name, vector)

			base_raster = do_raster_operation(rasters=[base_raster, base_raster_rainfall],
											  operation=RasterOperationEnum.DIVIDE, nodata=nodata)

			target_raster = do_raster_operation(rasters=[target_raster, target_raster_rainfall],
											  operation=RasterOperationEnum.DIVIDE, nodata=nodata)

		time_array = [x.raster_year for x in ndvi_models]
		
		"""
		stack pixel values. This will put all pixel values at specific location 
		into one single array such that values at the same location for different 
		pixel location will be contained in a single array. The array will be of size 
		(raster_rows, raster_cols, no_of_rasters)

		To get mean of rasters by their positions, use the below form
			np.mean(np.dstack([x, y, z]).transpose(), axis=0).transpose()
		"""
		rasters = np.dstack(ndvi_rasters)

		if len(ndvi_rasters) != len(time_array):
			error = _("The number of available datasets is different from the number of periods selected. Number of datasets is {0} while the number of periods is {1}. Ensure there is a dataset for each of the years within the reporting period."
					.format(len(ndvi_rasters), len(time_array)))
			return self.return_with_error(error)

		# Create dataframe
		df = pd.DataFrame()
		# create dynamic index for each reporting period
		for i, tm in enumerate(time_array):
			df[str(tm)] = ndvi_rasters[i].flatten()

		df['mapping'] = nodata #initialize all to nodata
		df['slope'] = nodata #initialize all to nodata
		df['pvalue'] = nodata #initialize all to nodata

		# create masks
		nodata_masks = []
		for i, tm in enumerate(time_array):
			msk = (df[str(tm)] == nodata)
			nodata_masks.append(msk)
	
		# Compute slope
		# 1.  compute slope		
		"""
		do linear regression on every pixel and for this 
		we are getting the r/ship btwn base and target years pixel values
		We only consider slope and the p_value. stats.linregress returns values as below
			slope, intercept, r_value, p_value, std_err = stats.linregress(time_array, data_array).
		linregress() uses Wald Test with t-distribution, not mann kandell, so we use kendalltau since
		we want to do a non-parametric significance test
		"""	
		# for those values that have not changed, the slope is 0
		df.loc[~np.logical_and.reduce(nodata_masks), ['slope']] = 0 # combine and apply masks

		# Only do regression where pixel values have changed
		df.loc[~np.logical_and.reduce(nodata_masks), ['slope']] = df.apply(lambda x: get_linear_regression(x), axis=1) 

		# get p value
		# 2. Compute pvalues to perform significance test
		"""
		If p Value is more than cutoff, then its stable.
		p value will be nan if both x and y are the same. if values 
		of x (base) and y (target) are same, it returns nan values.	
		"""
		# get p value where the base and target are different, else assign p value to 1.0
		df.loc[~np.logical_and.reduce(nodata_masks), ['pvalue']] = df.apply(lambda x: get_pvalue(x), axis=1) 
		
		# set mapping to stable first for all non-masked values
		df.loc[~np.logical_and.reduce(nodata_masks), ['mapping']] = TrajectoryChangeTernaryEnum.STABLE.key

		# 3. Set transitions. 
		"""
		Degraded: If pvalue <= ProductivitySettings.PVALUE_CUTOFF and slope < 0
		Improved: If pvalue <= ProductivitySettings.PVALUE_CUTOFF and slope > 0
		Stable: If pvalue > ProductivitySettings.PVALUE_CUTOFF or (pvalue <= ProductivitySettings.PVALUE_CUTOFF and slope = 0)
		"""
		significant_pvalue_mask = (df['pvalue'] <= ProductivitySettings.PVALUE_CUTOFF)
		
		# improved
		improved_mask = (df['slope'] >= 0)
		df.loc[~np.logical_and.reduce(nodata_masks) & improved_mask & significant_pvalue_mask, ['mapping']] = TrajectoryChangeTernaryEnum.IMPROVED.key
		
		# degraded
		degraded_mask = (df['slope'] < 0)
		df.loc[~np.logical_and.reduce(nodata_masks) & degraded_mask & significant_pvalue_mask, ['mapping']] = TrajectoryChangeTernaryEnum.DEGRADED.key

		# reshape the pd.series into 2d array
		out_raster = df['mapping'].values.reshape(ndvi_rasters[0].shape)

		# Clip the raster and save for later referencing
		meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)
		
		return return_raster_with_stats(
			request=self.request,
			datasource=out_raster, 
			prefix="traj", 
			change_enum=TrajectoryChangeTernaryEnum, 
			metadata_raster_path=meta_raster_path, #start_model.rasterfile.name, 
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=ProductivitySettings.SUB_DIR
		)

	def _calculate_trajectory_version2(self, start_year, end_year, return_raw=False, is_baseline=False):
		"""
		Calculate Trajectory sub-indicator using updated equations. Trajectory measures the rate of change in 
		primary productivity over time.

		Pass `start_year` and `end_year` as parameters to allow computation of values of baseline and 
		reporting period values separately.

		`return_raw` parameter determines if the results will be returned raw or processed

		Check:
			https://gitlab.com/locateit/oss-land-degradation-monitoring-service/oss-ldms/-/wikis/Land-Productivity-Sub-Indicator

		See:
			https://www.unccd.int/sites/default/files/relevant-links/2021-03/Indicator_15.3.1_GPG_v2_29Mar_Advanced-version.pdf
		
		Steps:
		1. Compute pixel level regression values. We only interested in the slope
		2. For each pixel, perform a Mann-Kendall significance test on the pixel values
		3. For those that pass the significance test, perform a transitional mapping 
		   to determine if degraded, stable or improved.
		4. Generate a raster containing the transitional values
		5. compute the raster statistics to be returned together with the raster
		"""
		def get_linear_regression(item):
			"""Get the slope"""
			# slope, intercept, r_value, p_value, std_err = stats.linregress(time_array, item['values'])
			data = extract_period_values(item)
			if data == nodata:
				return nodata		
			
			slope, intercept, r_value, p_value, std_err = stats.linregress(time_array, data)
			return slope

		def extract_period_values(item):
			data = []			
			# Extract values for all the periods to form the data series
			for i, tm in enumerate(time_array):
				val = item[str(tm)]
				if val == nodata: # if any value has nodata, then return nodata as val of slope
					return nodata
				data.append(val)
			return data

		def get_pvalue(item):
			"""Get pvalue"""
			data = extract_period_values(item)
			if data == nodata:
				return nodata	
			tau, p_value = stats.kendalltau(time_array, data)
			# tau, p_value = stats.kendalltau(time_array, [item['base'], item['target']])
			# p_value = p_value if not np.isnan(p_value) else 1.
			return p_value
		
		self.start_year = start_year
		self.end_year = end_year

		error, vector, start_model, end_model, start_year, end_year = self.prevalidate()
		if error:
			return self.return_with_error(error)

		ndvi_models = self.get_vi_raster_models(self.start_year, self.end_year)
		if not ndvi_models:
			return self.return_with_error(_("There are no {0} rasters for the selected periods {1} to {2}".format(
				self.veg_index, self.start_year, self.end_year)))

		if len(ndvi_models) < ProductivitySettings.MIN_RASTERS_FOR_TRAJECTORY_V2 and is_baseline:
			return self.return_with_error(_("A minimum of %s years of %s data is needed to compute trajectory" % (ProductivitySettings.MIN_RASTERS_FOR_TRAJECTORY_V2, self.raster_source.value)))

		start_model, end_model, error = self.get_start_and_end_ndvi_raster_models()
		if error:
			return self.return_with_error(error)
		
		# Extract raster meta data
		meta = get_raster_meta(start_model.rasterfile.name)
		nodata = meta['nodata']
		
		"""
		Extract pixels of the vector we are interested in.
		We ignore the rest of the raster
		"""
		ndvi_rasters = self.get_vi_rasters(self.start_year, self.end_year)

		# base_raster, nodata = extract_pixels_using_vector(start_model.rasterfile.name, vector, nodata)
		# target_raster, nodata = extract_pixels_using_vector(end_model.rasterfile.name, vector, nodata)

		if ProductivitySettings.USE_RUE_FOR_TRAJECTORY:
			# If we are using RUE, we compute NDIV/Rainfall and then use the result as
			# the input rasters.
			# if using RUE, use rainfall raster instead of computing slope
			# we divide NDVI by Rainfall to get RUE
			start_model_rainfall, error = self.get_rainfall_raster_model(self.start_year, throw_error=False)
			if error:
				return self.return_with_error(error)
			end_model_rainfall, error = self.get_rainfall_raster_model(self.end_year, throw_error=False)
			if error:
				return self.return_with_error(error)

			base_raster_rainfall, nodata, rastfile = extract_pixels_using_vector(start_model_rainfall.rasterfile.name, vector)
			target_raster_rainfall, nodata, rastfile = extract_pixels_using_vector(end_model_rainfall.rasterfile.name, vector)

			base_raster = do_raster_operation(rasters=[base_raster, base_raster_rainfall],
											  operation=RasterOperationEnum.DIVIDE, nodata=nodata)

			target_raster = do_raster_operation(rasters=[target_raster, target_raster_rainfall],
											  operation=RasterOperationEnum.DIVIDE, nodata=nodata)

		time_array = [x.raster_year for x in ndvi_models]
		
		"""
		stack pixel values. This will put all pixel values at specific location 
		into one single array such that values at the same location for different 
		pixel location will be contained in a single array. The array will be of size 
		(raster_rows, raster_cols, no_of_rasters)

		To get mean of rasters by their positions, use the below form
			np.mean(np.dstack([x, y, z]).transpose(), axis=0).transpose()
		"""
		rasters = np.dstack(ndvi_rasters)

		if len(ndvi_rasters) != len(time_array):
			error = _("The number of available datasets is different from the number of periods selected. Number of datasets is {0} while the number of periods is {1}. Ensure there is a dataset for each of the years within the reporting period."
					.format(len(ndvi_rasters), len(time_array)))
			return self.return_with_error(error)

		# Create dataframe
		df = pd.DataFrame()
		# create dynamic index for each reporting period
		for i, tm in enumerate(time_array):
			df[str(tm)] = ndvi_rasters[i].flatten()

		df['mapping'] = nodata #initialize all to nodata
		df['slope'] = nodata #initialize all to nodata
		df['pvalue'] = nodata #initialize all to nodata

		# create masks
		nodata_masks = []
		for i, tm in enumerate(time_array):
			msk = (df[str(tm)] == nodata)
			nodata_masks.append(msk)
	
		# Compute slope
		# 1.  compute slope		
		"""
		do linear regression on every pixel and for this 
		we are getting the r/ship btwn base and target years pixel values
		We only consider slope and the p_value. stats.linregress returns values as below
			slope, intercept, r_value, p_value, std_err = stats.linregress(time_array, data_array).
		linregress() uses Wald Test with t-distribution, not mann kandell, so we use kendalltau since
		we want to do a non-parametric significance test
		"""	
		# for those values that have not changed, the slope is 0
		df.loc[~np.logical_and.reduce(nodata_masks), ['slope']] = 0 # combine and apply masks

		# Only do regression where pixel values have changed
		df.loc[~np.logical_and.reduce(nodata_masks), ['slope']] = df.apply(lambda x: get_linear_regression(x), axis=1) 

		# get p value
		# 2. Compute pvalues to perform significance test
		"""
		If p Value is more than cutoff, then its stable.
		p value will be nan if both x and y are the same. if values 
		of x (base) and y (target) are same, it returns nan values.	
		"""
		# get p value where the base and target are different, else assign p value to 1.0
		df.loc[~np.logical_and.reduce(nodata_masks), ['pvalue']] = df.apply(lambda x: get_pvalue(x), axis=1) 
		
		# set mapping to stable first for all non-masked values
		# df.loc[~np.logical_and.reduce(nodata_masks), ['mapping']] = TrajectoryChangeTernaryEnum.STABLE.key

		# 3. Set transitions. 
		"""
		Degraded: If pvalue <= ProductivitySettings.PVALUE_CUTOFF and slope < 0
		Improved: If pvalue <= ProductivitySettings.PVALUE_CUTOFF and slope > 0
		Stable: If pvalue > ProductivitySettings.PVALUE_CUTOFF or (pvalue <= ProductivitySettings.PVALUE_CUTOFF and slope = 0)
		"""
		# significant_pvalue_mask = (df['pvalue'] <= ProductivitySettings.PVALUE_CUTOFF)
		
		# improved
		# improved_mask = (df['slope'] >= 0)
		# df.loc[~np.logical_and.reduce(nodata_masks) & improved_mask & significant_pvalue_mask, ['mapping']] = TrajectoryChangeTernaryEnum.IMPROVED.key
		
		# degraded
		# degraded_mask = (df['slope'] < 0)
		# df.loc[~np.logical_and.reduce(nodata_masks) & degraded_mask & significant_pvalue_mask, ['mapping']] = TrajectoryChangeTernaryEnum.DEGRADED.key

		# reshape the pd.series into 2d array
		out_raster = df['slope'].values.reshape(ndvi_rasters[0].shape)

		out_raster = self.mask_array(out_raster, nodata)
		# Clip the raster and save for later referencing
		meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)
		
		trend_enum, change_map = self.initialize_trajectory_matrix() 
		
		ds = out_raster
		df = pd.DataFrame({
						'ratio': ds.filled(fill_value=nodata).flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in change_map:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']
		
		out_raster = df['mapping'].values.reshape(ds.shape)
		out_raster = out_raster.astype(np.int32)

		if return_raw:
			return {
				'datasource': out_raster,
				'nodata': nodata,
				'resolution': start_model.resolution,
				'meta_path': meta_raster_path
			}
		return return_raster_with_stats(
			request=self.request,
			datasource=out_raster, 
			prefix="traj", 
			change_enum=trend_enum, 
			metadata_raster_path=meta_raster_path, #start_model.rasterfile.name, 
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=ProductivitySettings.SUB_DIR
		)

	def calculate_state(self):
		"""
		Calculate State sub-indicator.
		The Productivity State indicator allows for the detection of recent changes
		in primary productivity as compared to a baseline period.
		"""
		if self.compute_version == 2:
			if self.in_sub_indicator_context:
				return self._calculate_state_version2(start_year=self.start_year,
							end_year=self.end_year)
			else: # we are computing the main indicator where baseline is involved
				# get the state for the baseline period
				baseline_start_year = (self.baseline_end_year - ProductivitySettings.MIN_RASTERS_FOR_STATE_V2) + 1
				reporting_period_start_year = (self.end_year - ProductivitySettings.MIN_COMPARISON_RANGE) + 1
				original_end_year = copy.copy(self.end_year)

				baseline = self._calculate_state_version2(start_year=baseline_start_year,
							end_year=self.baseline_end_year, return_raw=True)
				if self.error:
					return self.return_with_error(self.error)

				self.end_year = original_end_year
				# get state for reporting period
				reporting = self._calculate_state_version2(start_year=reporting_period_start_year,
							end_year=self.end_year, return_raw=True)
				if self.error:
					return self.return_with_error(self.error)

				change_matrix = self.initialize_state_change_matrix()

				df = pd.DataFrame({
								'baseline': baseline['datasource'].flatten(),
								'reporting': reporting['datasource'].flatten(),
							})
				df['mapping'] = reporting['nodata']

				# Replace values
				for row in change_matrix:
					# filter all matching entries as per the matrix
					mask = (df['baseline'] == row['base']) & (df['reporting'] == row['curr'])
					df.loc[mask, ['mapping']] = row['mapping']
				
				datasource = df['mapping'].values.reshape(baseline['datasource'].shape)
				datasource = datasource.astype(np.int32)

				return return_raster_with_stats(
					request=self.request,
					datasource=datasource, 
					prefix="state", 
					change_enum=StateChangeBinaryEnum,
					metadata_raster_path=reporting['meta_path'],
					nodata=reporting['nodata'], 
					resolution=reporting['resolution'],
					start_year=baseline_start_year,
					end_year=self.end_year,
					subdir=ProductivitySettings.SUB_DIR 
				)
			
		return self._calculate_state_version1()

	def _calculate_state_version1(self):
		"""
		Calculate State sub-indicator.
		The Productivity State indicator allows for the detection of recent changes
		in primary productivity as compared to a baseline period.	

		Steps:
		BASELINE PERIOD:
			1. Determine baseline period, iteally it is 2000-2015.
			2. For each of the years comprising the baseline period, get the mean 
			   per pixel for each of the rasters
			3. Get the unique values of the pixel values for the baseline period
			4. Get the range of observed values i.e (highest - lowest) pixel value
			5. Add 5% of the range to the highest observed value
			6. Subtract 5% of the range from the lowest observed value
		COMPARISON PERIOD:
			1. This comprises of start period and end period but they have to be 3 years apart
			2. Repeat the same process we did for each year in the baseline period
			3. The output will be one raster comprising the percentile classes associated
			   with the mean pixel value which is calculated by getting the average of the
			   pixel values for each of the years in the comparison period
		ANALYIS:
			1. Subtract the classes associated with comparison period from the class associated 
			   with the baseline period.
			2. Tag the pixel as improved, degraded or stable

		TODO: https://github.com/jmcarpenter2/swifter
		"""		
		
		error, vector, start_model, end_model, start_year, end_year = self.prevalidate()
		if error:
			return self.return_with_error(error)

		start_model, end_model, error = self.get_start_and_end_ndvi_raster_models()
		if error:
			return self.return_with_error(error)

		# Extract raster meta data
		meta = get_raster_meta(start_model.rasterfile.name)
		nodata = meta['nodata']

		"""
		Extract pixels of the vector we are interested in.
		We ignore the rest of the raster
		"""

		# Clip the raster and save for later referencing
		meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)
		
		base_raster, nodata, rastfile = extract_pixels_using_vector(start_model.rasterfile.name, vector)
		target_raster, nodata, rastfile = extract_pixels_using_vector(end_model.rasterfile.name, vector)
		
		error = self.validate_state_rasters()
		if error and ProductivitySettings.ENFORCE_MIN_RASTERS_FOR_STATE:
			return self.return_with_error(error)

		time_array = (start_year, end_year)
		
		# Step 1
		"""
		For each pixel, use the annual integrals of NDVI for the baseline period to compute 
		a frequency distribution. In case the baseline period missed some extreme values in NDVI,
		add 5% on both extremes of the distribution. That expanded frequency distribution 
		curve is then used to define the cut-off values of the 10 percentile classes.

		Compute the mean NDVI for the baseline period, and determine the percentile class 
		it belongs to. Assign to the mean NDVI for the baseline period the number corresponding 
		to that percentile class. Possible values range from 1 (lowest class) to 10 (highest class).
		"""
		baseline_period, comparison_period = self.get_period_extents()
		# Get rasters for the baseline period
		# base_line_rasters = self.get_vi_rasters(ProductivitySettings.BASELINE_START, ProductivitySettings.BASELINE_END)
		if not baseline_period:
			return self.return_with_error(_("There must be data for at least %s years in order to compute state" % (ProductivitySettings.MIN_COMPARISON_RANGE)))

		base_line_rasters = self.get_vi_rasters(baseline_period[0], baseline_period[-1])
		base_line_rasters = reshape_rasters(base_line_rasters)

		# compute the per pixel average for all the baseline rasters
		base_line_avg_raster = self.compute_pixel_averages(rasters=base_line_rasters)
		
		# get frequency distribution for pixel values in the combined baseline raster
		freq_dist = self.get_frequency_distribution([base_line_avg_raster], nodata)
		
		# extend the freq distribution if need be
		freq_dist = self.extend_frequency_distributions(freq_dist)
		
		# assign percentile to each pixel
		base_raster = self.assign_percentiles(base_line_avg_raster, freq_dist, nodata=nodata)

		# Step 2
		"""
		Compute the mean NDVI for the comparison period, and determine the percentile 
		class it belongs to. Assign to the mean NDVI for the comparison period the number 
		corresponding to that percentile class. Possible values range 
		from 1 (lowest class) to 10 (highest class).
		We repeat the same process we did for baseline period
		"""
		# Get rasters for the comparison period
		# comparison_rasters = self.get_vi_rasters(self.start_year, self.end_year)
		comparison_rasters = self.get_vi_rasters(comparison_period[0], comparison_period[-1])	
		comparison_rasters = reshape_rasters(comparison_rasters)

		# compute the per pixel average for all the baseline rasters
		comparison_avg_raster = self.compute_pixel_averages(rasters=comparison_rasters)
		
		# get frequency distribution for pixel values in the combined 		baseline raster
		freq_dist = self.get_frequency_distribution([comparison_avg_raster], nodata)
		
		# extend the freq distribution if need be
		freq_dist = self.extend_frequency_distributions(freq_dist)
		
		# assign percentile to each pixel
		comparison_raster = self.assign_percentiles(comparison_avg_raster, freq_dist, nodata=nodata)

		# Step 3
		"""
		Subtract comparison from baseline. Transitions are : 
		Degraded: If change <= 2
		Improved: If change >= 2
		Stable: If -2<=change<=2
		"""
		df = pd.DataFrame({'base': base_raster.flatten(), 'target': comparison_raster.flatten()})		
		df['mapping'] = nodata #initialize all to nodata

		nodata_mask = (df['base'] == nodata) | (df['target'] == nodata)
		df.loc[~nodata_mask, ['diff']] = df['target'] - df['base']
		
		# set mapping to stable first for all non-masked values
		df.loc[~nodata_mask, ['mapping']] = StateChangeTernaryEnum.STABLE.key		
		
		improved_mask = (df['diff'] > ProductivitySettings.STATE_CHANGE_POSITIVE_CUTOFF)
		df.loc[~nodata_mask & improved_mask, ['mapping']] = StateChangeTernaryEnum.IMPROVED.key

		degraded_mask = (df['diff'] < ProductivitySettings.STATE_CHANGE_NEGATIVE_CUTOFF)
		df.loc[~nodata_mask & degraded_mask, ['mapping']] = StateChangeTernaryEnum.DEGRADED.key

		out_raster = df['mapping'].values.reshape(base_raster.shape)

		return return_raster_with_stats(
			request=self.request,
			datasource=out_raster, 
			prefix="state", 
			change_enum=StateChangeTernaryEnum, 
			metadata_raster_path=meta_raster_path, #start_model.rasterfile.name, 
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=ProductivitySettings.SUB_DIR
		)

	def _calculate_state_version2(self, start_year, end_year, return_raw=False):
		"""
		Calculate State sub-indicator with updated equations.
		The Productivity State indicator allows for the detection of recent changes
		in primary productivity as compared to a baseline period.	

		Pass `start_year` and `end_year` as parameters to allow computation of values of baseline and 
		reporting period values separately.

		`return_raw` parameter determines if the results will be returned raw or processed

		Check:
			https://gitlab.com/locateit/oss-land-degradation-monitoring-service/oss-ldms/-/wikis/Land-Productivity-Sub-Indicator

		See:
			https://www.unccd.int/sites/default/files/relevant-links/2021-03/Indicator_15.3.1_GPG_v2_29Mar_Advanced-version.pdf
		Steps:
		* Get the image collection for the baseline period (2000 to 2015)
		* Separate the collection into two i.e the first 12 years (2000-2012) and last 3 years (2013 - 2015)
		* Compute the normal distribution of the NDVI (mean and standard deviation) for the first 12years. For the remaining three years compute the mean only.
		* Compute the z statistics by subtracting the mean of the first 12 years from the mean of the last three years, divided by the standard deviation from the first 12 years divided by squareroot of 3.
		* Classify the z scores using the thresholds either using 3 or 5 class map
	
		COMPARISON PERIOD:
			1. This comprises of start period and end period but they have to be 3 years apart
			2. Repeat the same process we did for each year in the baseline period
		ANALYIS:
			1. Subtract the classes associated with comparison period from the class associated 
			   with the baseline period.
			2. Tag the pixel as improved, degraded or stable

		TODO: https://github.com/jmcarpenter2/swifter
		"""		
		def compute_z_statistics():
			"""Compute the Z statistics
			"""			
			zscores = (self.mask_array(comparison_avg_raster, nodata=nodata) - self.mask_array(base_line_avg_raster, nodata=nodata)) / (self.mask_array(baseline_stddev_raster, nodata=nodata) / np.sqrt(3))
			return zscores

		self.start_year = start_year
		self.end_year = end_year

		error, vector, start_model, end_model, start_year, end_year = self.prevalidate(both_valid=True)
		if error:
			return self.return_with_error(error)

		start_model, end_model, error = self.get_start_and_end_ndvi_raster_models(both_valid=True)
		if error:
			return self.return_with_error(error)

		# Extract raster meta data
		meta = get_raster_meta(start_model.rasterfile.name)
		nodata = meta['nodata']

		"""
		Extract pixels of the vector we are interested in.
		We ignore the rest of the raster
		""" 
		# Clip the raster and save for later referencing
		meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)
		
		base_raster, nodata, rastfile = extract_pixels_using_vector(start_model.rasterfile.name, vector)
		target_raster, nodata, rastfile = extract_pixels_using_vector(end_model.rasterfile.name, vector)
		
		error = self.validate_state_rasters()
		if error and ProductivitySettings.ENFORCE_MIN_RASTERS_FOR_STATE:
			return self.return_with_error(error)

		time_array = (start_year, end_year)
		
		# Step 1
		"""
		For each pixel, use the annual integrals of NDVI for the baseline period to compute 
		a frequency distribution. In case the baseline period missed some extreme values in NDVI,
		add 5% on both extremes of the distribution. That expanded frequency distribution 
		curve is then used to define the cut-off values of the 10 percentile classes.

		Compute the mean NDVI for the baseline period, and determine the percentile class 
		it belongs to. Assign to the mean NDVI for the baseline period the number corresponding 
		to that percentile class. Possible values range from 1 (lowest class) to 10 (highest class).
		"""
		baseline_period, comparison_period = self.get_period_extents()
		# Get rasters for the baseline period
		if not baseline_period:
			return self.return_with_error(_("There must be data for at least %s years in order to compute state" % (ProductivitySettings.MIN_COMPARISON_RANGE)))

		base_line_rasters = self.get_vi_rasters(baseline_period[0], baseline_period[-1])
		base_line_rasters = reshape_rasters(base_line_rasters)

		# compute the per pixel average for all the baseline rasters
		base_line_avg_raster = self.compute_pixel_averages(rasters=base_line_rasters)

		# compute std dev for all the baseline rasters
		baseline_stddev_raster = self.compute_std_deviation(rasters=base_line_rasters)
				
		# Step 2
		"""
		Compute the mean NDVI for the comparison period, and determine the percentile 
		class it belongs to. Assign to the mean NDVI for the comparison period the number 
		corresponding to that percentile class. Possible values range 
		from 1 (lowest class) to 10 (highest class).
		We repeat the same process we did for baseline period
		"""
		# Get rasters for the comparison period
		comparison_rasters = self.get_vi_rasters(comparison_period[0], comparison_period[-1])	
		comparison_rasters = reshape_rasters(comparison_rasters)
 
		# compute the per pixel average for all the baseline rasters
		comparison_avg_raster = self.compute_pixel_averages(rasters=comparison_rasters)
	
		# compute Z stats
		z_stats = compute_z_statistics()

		# Step 3
		state_enum, change_map = self.initialize_state_matrix() 
		
		df = pd.DataFrame({
						'ratio': z_stats.filled(fill_value=nodata).flatten(),												
					})
		df['mapping'] = nodata
		no_data_mask = df['ratio'] != nodata
		# Replace values
		for row in change_map:
			# filter all matching entries as per the matrix
			mask = (df['ratio'] >= row['low']) & (df['ratio'] < row['high'])
			df.loc[mask & no_data_mask, ['mapping']] = row['mapping']
		
		out_raster = df['mapping'].values.reshape(z_stats.shape)
		out_raster = out_raster.astype(np.int32)

		if return_raw:
			return {
				'datasource': out_raster,
				'nodata': nodata,
				'resolution': start_model.resolution,
				'meta_path': meta_raster_path
			}
		return return_raster_with_stats(
			request=self.request,
			datasource=out_raster, 
			prefix="state", 
			change_enum=state_enum, 
			metadata_raster_path=meta_raster_path,
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=ProductivitySettings.SUB_DIR
		)

	def mask_array(self, rast, nodata):
		"""Mask nodata values
		"""
		ma_rast = ma.array(rast)
		ma_rast[ma_rast==nodata] = ma.masked
		return ma_rast

	def validate_state_rasters(self):
		"""
		Validate that we have enough raters to compute state.
		Convention is to have at least 10 rasters
		"""
		rasters = get_raster_models(
						raster_category=self.veg_index, 
						raster_source=self.raster_source.value,
						raster_year__lte=self.end_year,
						admin_zero_id=self.admin_0)

		min_rasters = ProductivitySettings.MIN_RASTERS_FOR_STATE if self.compute_version == 1 else ProductivitySettings.MIN_RASTERS_FOR_STATE_V2
		if rasters.count() < min_rasters:
			return _("""You need at least %s years of data until %s inorder to 
									compute productivity""" % (min_rasters, self.end_year))
	
	def validate_performance_rasters(self):
		"""
		Validate that we have enough raters to compute performance.
		Convention is to have at least 15 rasters
		"""
		rasters = get_raster_models(
						raster_category=self.veg_index, 
						raster_source=self.raster_source.value,
						raster_year__lte=self.end_year,
						admin_zero_id=self.admin_0)

		min_rasters = ProductivitySettings.MIN_RASTERS_FOR_PERFORMANCE_V2 if self.compute_version == 1 else ProductivitySettings.MIN_RASTERS_FOR_PERFORMANCE_V2
		if rasters.count() < min_rasters:
			return _("""You need at least %s years of data until %s inorder to 
									compute productivity""" % (min_rasters, self.end_year))
	
	def get_period_extents(self):
		"""
		Splits the reporting periods into baseline and comparison periods

		The last three years will be the comparison period. the rest will be 
		the baseline period. For example, if a user select 2001 - 2013, 
		comparison period will be 2011-2013, while the baseline period will be 2001-2010
		"""
		# get list of available rasters
		rasters = get_raster_models(#raster_type=self.raster_type, 
						raster_category=self.veg_index, 
						raster_source=self.raster_source.value,
						raster_year__lte=self.end_year,
						admin_zero_id=self.admin_0)
		periods = sorted([x.raster_year for x in rasters])
		
		# Get the other periods except the last N periods
		baseline_period = periods[:-ProductivitySettings.MIN_COMPARISON_RANGE:]

		# Get the last N periods
		comparison_period = periods[-ProductivitySettings.MIN_COMPARISON_RANGE::]		
		return (baseline_period, comparison_period)

	def get_vi_rasters(self, start_period, end_period):
		"""Get rasters between start and end periods

		Args:
			start_year (int): Start period
			end_year (int): End period
		"""
		rasters_list = []
		vector, error = self.get_vector()	
		period = start_period
		min_shape = None # store smallest array size
		while period <= end_period:
			model, error = self.get_vi_raster_model(period, throw_error=False)
			if model:
				# Extract raster meta data
				meta = get_raster_meta(model.rasterfile.name)				
				"""
				Extract pixels of the vector we are interested in.
				We ignore the rest of the raster
				"""
				raster, nodata, rastfile = extract_pixels_using_vector(model.rasterfile.name, vector)				
				rasters_list.append(raster)
			period += 1
		return rasters_list
		
	def get_frequency_distribution(self, rasters, nodata):
		"""Get the frequency distribution for different rasters 
		Return:
			An array with counts for each unique value
		"""
		uniques = []
		for rast in rasters:
			unique, counts = np.unique(rast[rast != nodata], return_counts=True)
			# convert to {val:count} dictionary
			freq_dists = dict(zip(unique, counts)) 
			uniques.append(freq_dists)

		# Sum along the dict keys
		counter = collections.Counter()
		for d in uniques:
			counter.update(d)
		return dict(counter)		
	
	def extend_frequency_distributions(self, freq_dist):
		"""Add some % to highest pixel value and deduct 5% from
		the lowest value. The resulting value should be 
		between -1 and +1 which are the valid values of NDVI

		Args:
			freq_dist (dict): Dictionary of value { pixel_val: pixel_count }
		""" 
		# sort dict by key since key is the pixel value
		dct = list(sorted(freq_dist.items(), key=lambda x: int(x[0]) if not math.isnan(x[0]) and not math.isinf(x[0]) else x[0], reverse=True))
		
		first_item, last_item = dct[0], dct[-1]
		# get range btwn max and min pixel vals
		cur_max, cur_min = dct[0][0], dct[-1][0] 		
		val_range = cur_max - cur_min

		# adjustment factor should be the range * PERC_FREQ_ADJUSTMENT
		adjustment_factor = val_range * ProductivitySettings.PERC_FREQ_ADJUSTMENT * 0.01
		
		# Since the current pixel vals have been multiplied by ProductivitySettings.DIVISION_FACTOR,
		# we need to consider this when doing validation
		# adjust max value but only to a max of +1
		max_val = cur_max + adjustment_factor
		if max_val > 1 * ProductivitySettings.DIVISION_FACTOR:
			max_val = 1 * ProductivitySettings.DIVISION_FACTOR
		
		# adjust min value but only to a min of -1
		min_val = cur_min - adjustment_factor
		if min_val < (-1 * ProductivitySettings.DIVISION_FACTOR):
			min_val = -1 * ProductivitySettings.DIVISION_FACTOR
		
		# replace the high and lowest keys
		freq_dist[max_val] = freq_dist[cur_max]
		del freq_dist[cur_max]

		freq_dist[min_val] = freq_dist[cur_min]
		del freq_dist[cur_min]

		return freq_dist

	def compute_pixel_averages(self, rasters):
		"""Calculate average pixel values for different rasters 
		
		Return:
			A raster whose values are the average of different values per pixel
		"""
		# use axis=0 so that it returns the mean per pixel correctly
		if not isinstance(rasters, list): # np.ndarray):
			rasters = [rasters]
		avg_raster = np.mean(rasters, axis=0)
		return avg_raster

	def compute_std_deviation(self, rasters):
		"""Calculate standard deviation for different rasters 
		
		Return:
			A value are the std dev of different values per pixel
		"""
		# use axis=0 so that it returns the mean per pixel correctly
		std_raster = np.std(rasters, axis=0)
		return std_raster

	def initialize_state_matrix(self):
		"""
		Initialize State matrix. Return a tuple of (EnumClass, mapping)
		"""
		map_matrix = (None, [])
		if self.in_sub_indicator_context:
			if self.class_map == THREE_CLASS_MAP:
				map_matrix = (StateChangeTernaryEnum, [
					{#1
						'low': MIN_INT,
						'high': -1.28,
						'mapping': StateChangeTernaryEnum.DEGRADED.key
					},
					{#2
						'low': -1.28,
						'high': 1.28,
						'mapping': StateChangeTernaryEnum.STABLE.key
					},
					{#3
						'low': 1.28,
						'high': MAX_INT,
						'mapping': StateChangeTernaryEnum.IMPROVED.key
					},
				])
			elif self.class_map == FIVE_CLASS_MAP:
				map_matrix = (StateChangeQuinaryEnum, [
					{#1
						'low': MIN_INT,
						'high': -1.96,
						'mapping': StateChangeQuinaryEnum.DEGRADED.key
					},
					{#2
						'low': -1.96,
						'high': -1.28,
						'mapping': StateChangeQuinaryEnum.RISK_OF_DEGRADING.key
					},
					{#3
						'low': -1.28,
						'high': 1.28,
						'mapping': StateChangeQuinaryEnum.NO_CHANGE.key
					},
					{#4
						'low': 1.28,
						'high': 1.96,
						'mapping': StateChangeQuinaryEnum.POTENTIALLY_IMPROVING.key
					},
					{#5
						'low': 1.96,
						'high': MAX_INT,
						'mapping': StateChangeQuinaryEnum.IMPROVING.key
					},			
				])
		else:# If we computing main indicator set as binary values
			map_matrix = (StateChangeBinaryEnum, [
				{#1
					'low': MIN_INT,
					'high': -1.96,
					'mapping': StateChangeBinaryEnum.DEGRADED.key
				},
				{#2
					'low': -1.96,
					'high': MAX_INT,
					'mapping': StateChangeBinaryEnum.NOT_DEGRADED.key
				},
			])
		return map_matrix

	def initialize_state_change_matrix(self):
		"""
		Initialize state matrix to compare baseline with reporting period values
		"""
		matrix = [
			{#1
				'base': StateChangeBinaryEnum.DEGRADED.key,
				'curr': StateChangeBinaryEnum.DEGRADED.key,
				'mapping': StateChangeBinaryEnum.DEGRADED.key
			},
			{#2
				'base': StateChangeBinaryEnum.NOT_DEGRADED.key,
				'curr': StateChangeBinaryEnum.DEGRADED.key,
				'mapping': StateChangeBinaryEnum.DEGRADED.key
			},
			{#3
				'base': StateChangeBinaryEnum.DEGRADED.key,
				'curr': StateChangeBinaryEnum.NOT_DEGRADED.key,
				'mapping': StateChangeBinaryEnum.NOT_DEGRADED.key
			},
			{#4
				'base': StateChangeBinaryEnum.NOT_DEGRADED.key,
				'curr': StateChangeBinaryEnum.NOT_DEGRADED.key,
				'mapping': StateChangeBinaryEnum.NOT_DEGRADED.key
			}
		]
		return matrix

	def initialize_trajectory_matrix(self):
		"""
		Initialize State matrix. Return a tuple of (EnumClass, mapping)
		"""
		map_matrix = (None, [])
		if self.in_sub_indicator_context:
			if self.class_map == THREE_CLASS_MAP:
				map_matrix = (TrajectoryChangeTernaryEnum, [
					{#1
						'low': MIN_INT,
						'high': -1.28,
						'mapping': TrajectoryChangeTernaryEnum.DEGRADED.key
					},
					{#2
						'low': -1.28,
						'high': 1.28,
						'mapping': TrajectoryChangeTernaryEnum.STABLE.key
					},
					{#3
						'low': 1.28,
						'high': MAX_INT,
						'mapping': TrajectoryChangeTernaryEnum.IMPROVED.key
					},
				])
			elif self.class_map == FIVE_CLASS_MAP:
				map_matrix = (TrajectoryChangeQuinaryEnum, [
					{#1
						'low': MIN_INT,
						'high': -1.96,
						'mapping': TrajectoryChangeQuinaryEnum.DEGRADED.key
					},
					{#2
						'low': -1.96,
						'high': -1.28,
						'mapping': TrajectoryChangeQuinaryEnum.RISK_OF_DEGRADING.key
					},
					{#3
						'low': -1.28,
						'high': 1.28,
						'mapping': TrajectoryChangeQuinaryEnum.NO_CHANGE.key
					},
					{#4
						'low': 1.28,
						'high': 1.96,
						'mapping': TrajectoryChangeQuinaryEnum.POTENTIALLY_IMPROVING.key
					},
					{#5
						'low': 1.96,
						'high': MAX_INT,
						'mapping': TrajectoryChangeQuinaryEnum.IMPROVING.key
					},			
				])
		else:# If we computing main indicator set as binary values
			map_matrix = (TrajectoryChangeBinaryEnum, [
				{#1
					'low': MIN_INT,
					'high': -1.96,
					'mapping': TrajectoryChangeBinaryEnum.DEGRADED.key
				},
				{#2
					'low': -1.96,
					'high': MAX_INT,
					'mapping': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key
				},
			])
		return map_matrix

	def initialize_trajectory_change_matrix(self):
		"""
		Initialize trajectory matrix to compare baseline with reporting period values
		"""
		matrix = [
			{#1
				'base': TrajectoryChangeBinaryEnum.DEGRADED.key,
				'curr': TrajectoryChangeBinaryEnum.DEGRADED.key,
				'mapping': TrajectoryChangeBinaryEnum.DEGRADED.key
			},
			{#2
				'base': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key,
				'curr': TrajectoryChangeBinaryEnum.DEGRADED.key,
				'mapping': TrajectoryChangeBinaryEnum.DEGRADED.key
			},
			{#3
				'base': TrajectoryChangeBinaryEnum.DEGRADED.key,
				'curr': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key,
				'mapping': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key
			},
			{#4
				'base': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key,
				'curr': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key,
				'mapping': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key
			}
		]
		return matrix

	def initialize_performance_change_matrix(self):
		"""
		Initialize performance matrix to compare baseline with reporting period values
		"""
		matrix = [
			{#1
				'base': PerformanceChangeBinaryEnum.DEGRADED.key,
				'curr': PerformanceChangeBinaryEnum.DEGRADED.key,
				'mapping': PerformanceChangeBinaryEnum.DEGRADED.key
			},
			{#2
				'base': PerformanceChangeBinaryEnum.STABLE.key,
				'curr': PerformanceChangeBinaryEnum.DEGRADED.key,
				'mapping': PerformanceChangeBinaryEnum.DEGRADED.key
			},
			{#3
				'base': PerformanceChangeBinaryEnum.DEGRADED.key,
				'curr': PerformanceChangeBinaryEnum.STABLE.key,
				'mapping': PerformanceChangeBinaryEnum.STABLE.key
			},
			{#4
				'base': PerformanceChangeBinaryEnum.STABLE.key,
				'curr': PerformanceChangeBinaryEnum.STABLE.key,
				'mapping': PerformanceChangeBinaryEnum.STABLE.key
			}
		]
		return matrix

	def assign_percentiles(self, raster, freq_dist, nodata):
		"""
		Assign percentile to each pixel 
		
		Args:
			raster (array): Raster for which to assign percentiles
			freq_dist (dist): Dict containing {pixel_value: pixel_count}

		Returns:
			Raster whose values are the different percentile classes

		TODO : https://engineering.upside.com/a-beginners-guide-to-optimizing-pandas-code-for-speed-c09ef2c6a4d6
		"""

		def get_percentile(val):
			return percentileofscore(unique_vals, val)

		raster_shape = raster.shape

		# create an ndarray of unique values to speed up operations
		unique_vals = np.array(list(freq_dist.keys())) #rem the keys rep the unique pixel val
	
		df = pd.DataFrame({'item': raster.flatten()})
		df['percentile'] = nodata

		df.loc[df['item'] != nodata, ['percentile']] = df['item'].map(lambda x: percentileofscore(unique_vals, x) if x != nodata else nodata, na_action='ignore')
		return df['percentile'].values.reshape(raster_shape)
	
	def calculate_performance(self):
		"""
		Calculate Performance sub-indicator.
		The Productivity Performance indicator allows for the detection of recent changes
		in primary productivity as compared to a baseline period.
		"""
		if self.compute_version == 2:
			if self.in_sub_indicator_context:
				return self._calculate_performance_version2(start_year=self.start_year,
							end_year=self.end_year)
			else: # we are computing the main indicator where baseline is involved
				# get the state for the baseline period
				baseline_start_year = (self.baseline_end_year - ProductivitySettings.MIN_RASTERS_FOR_PERFORMANCE_V2) + 1
				reporting_period_start_year = (self.end_year - ProductivitySettings.MIN_COMPARISON_RANGE) + 1
				original_end_year = copy.copy(self.end_year)

				baseline = self._calculate_performance_version2(start_year=baseline_start_year,
							end_year=self.baseline_end_year, return_raw=True)
				if self.error:
					return self.return_with_error(self.error)

				self.end_year = original_end_year
				# get state for reporting period
				reporting = self._calculate_performance_version2(start_year=reporting_period_start_year,
							end_year=self.end_year, return_raw=True)
				if self.error:
					return self.return_with_error(self.error)

				change_matrix = self.initialize_performance_change_matrix()

				df = pd.DataFrame({
								'baseline': baseline['datasource'].flatten(),
								'reporting': reporting['datasource'].flatten(),
							})
				df['mapping'] = reporting['nodata']

				# Replace values
				for row in change_matrix:
					# filter all matching entries as per the matrix
					mask = (df['baseline'] == row['base']) & (df['reporting'] == row['curr'])
					df.loc[mask, ['mapping']] = row['mapping']
				
				datasource = df['mapping'].values.reshape(baseline['datasource'].shape)
				datasource = datasource.astype(np.int32)

				return return_raster_with_stats(
					request=self.request,
					datasource=datasource, 
					prefix="perf", 
					change_enum=StateChangeBinaryEnum,
					metadata_raster_path=reporting['meta_path'],
					nodata=reporting['nodata'], 
					resolution=reporting['resolution'],
					start_year=baseline_start_year,
					end_year=self.end_year,
					subdir=ProductivitySettings.SUB_DIR 
				)
			
		return self._calculate_performance_version1()
	
	def _calculate_performance_version1(self):
		"""
		Calculate Performance sub-indicator

		1. Compute pixel level mean NDVI
		2. Create ecological units (intersection of LC and Soil Type)
		3. Get NDVI frequency distribution
		4. Compute 90th percentile for mean ndvi vals for each unique eco unit. This is the max ndvi
		5. Compute mean_ndvi / max_ndvi ratio
		6. If ratio >= 0.5 then stable else degraded
		"""
		reference_eco_unit_model = get_raster_models(id=self.reference_eco_units).first()
		if not reference_eco_unit_model:
			return self.return_with_error(_("No raster is associated with the reference ecological units specified [%s]" % (self.reference_eco_units)))

		start_year, end_year, error = self.validate_periods()
		
		vector, error = self.get_vector()	
		if error:
			return self.return_with_error(error)

		start_model, end_model, error = self.get_start_and_end_ndvi_raster_models()
		if error:
			return self.return_with_error(error)

		# Extract raster meta data
		meta = get_raster_meta(start_model.rasterfile.name)
		nodata = meta['nodata']
		
		# Clip the raster and save for later referencing
		meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)
	
		"""
		Reproject ndvi_start_raster, ndvi_end_raster and soil_grid_raster based on base_lc_cover raster
		"""
		# reproject soil raster to modis resolution
		reprojected_eco_units_raster_file, nodata = reproject_raster(reference_raster=start_model.rasterfile.name, 
											  raster=reference_eco_unit_model.rasterfile.name,
											  resampling=Resampling.nearest)
		
		# Read reprojected raster
		reference_eco_units_raster, nodata, rastfile = extract_pixels_using_vector(
									reprojected_eco_units_raster_file, 
									vector, nodata)
	
		# Get rasters for the reporting period
		comparison_rasters = self.get_vi_rasters(self.start_year, self.end_year)
		
		datasource = self._do_compute_performance(comparison_rasters, base_rasters=reference_eco_units_raster, nodata=nodata)

		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="perf", 
			change_enum=PerformanceChangeBinaryEnum, 
			metadata_raster_path=meta_raster_path,  
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=ProductivitySettings.SUB_DIR
		) 

	def _calculate_performance_version2_deprecated(self, start_year, end_year, return_raw=False):
		"""
		Calculate Performance sub-indicator

		Pass `start_year` and `end_year` as parameters to allow computation of values of baseline and 
		reporting period values separately.

		`return_raw` parameter determines if the results will be returned raw or processed

		1. Compute pixel level mean NDVI for previous 15 years
		2. Compute 90th percentile for mean ndvi vals for each unique eco unit. This is the max ndvi
		3. Compute mean_ndvi / max_ndvi ratio
		4. If ratio >= 0.5 then stable else degraded
		"""
		self.start_year = start_year
		self.end_year = end_year

		start_year, end_year, error = self.validate_periods()
		
		vector, error = self.get_vector()	
		if error:
			return self.return_with_error(error)

		start_model, end_model, error = self.get_start_and_end_ndvi_raster_models()
		if error:
			return self.return_with_error(error)

		# Extract raster meta data
		meta = get_raster_meta(start_model.rasterfile.name)
		nodata = meta['nodata']
		
		# Clip the raster and save for later referencing
		meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)

		error = self.validate_performance_rasters()
		if error and ProductivitySettings.ENFORCE_MIN_RASTERS_FOR_PERFORMANCE:
			return self.return_with_error(error)

		time_array = (start_year, end_year)
		
		# Step 1
		"""
		For each pixel, use the annual integrals of NDVI for the baseline period to compute 
		a frequency distribution. In case the baseline period missed some extreme values in NDVI,
		add 5% on both extremes of the distribution. That expanded frequency distribution 
		curve is then used to define the cut-off values of the 10 percentile classes.

		Compute the mean NDVI for the baseline period, and determine the percentile class 
		it belongs to. Assign to the mean NDVI for the baseline period the number corresponding 
		to that percentile class. Possible values range from 1 (lowest class) to 10 (highest class).
		"""
		baseline_period, comparison_period = self.get_period_extents()
		# Get rasters for the baseline period
		if not baseline_period:
			return self.return_with_error(_("There must be data for at least %s years in order to compute performance" % (ProductivitySettings.MIN_COMPARISON_RANGE)))

		base_line_rasters = self.get_vi_rasters(baseline_period[0], baseline_period[-1])
		base_line_rasters = reshape_rasters(base_line_rasters)

		# Step 2
		"""
		Compute the mean NDVI for the comparison period, and determine the percentile 
		class it belongs to. Assign to the mean NDVI for the comparison period the number 
		corresponding to that percentile class. Possible values range 
		from 1 (lowest class) to 10 (highest class).
		We repeat the same process we did for baseline period
		"""
		# Get rasters for the comparison period
		comparison_rasters = self.get_vi_rasters(comparison_period[0], comparison_period[-1])	
		comparison_rasters = reshape_rasters(comparison_rasters)
 		
		datasource = self._do_compute_performance(comparison_rasters, base_rasters=base_line_rasters, nodata=nodata)

		if return_raw:
			return {
				'datasource': datasource,
				'nodata': nodata,
				'resolution': start_model.resolution,
				'meta_path': meta_raster_path
			}
		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="perf", 
			change_enum=PerformanceChangeBinaryEnum, 
			metadata_raster_path=meta_raster_path,  
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=ProductivitySettings.SUB_DIR
		) 

	def _calculate_performance_version2(self, start_year, end_year, return_raw=False):
		"""
		Calculate Performance sub-indicator

		Pass `start_year` and `end_year` as parameters to allow computation of values of baseline and 
		reporting period values separately.

		`return_raw` parameter determines if the results will be returned raw or processed

		1. Compute pixel level mean NDVI for previous 15 years
		2. Compute 90th percentile for mean ndvi vals for each unique eco unit. This is the max ndvi
		3. Compute mean_ndvi / max_ndvi ratio
		4. If ratio >= 0.5 then stable else degraded
		"""	
		self.start_year = start_year
		self.end_year = end_year

		reference_eco_unit_model = get_raster_models(id=self.reference_eco_units).first()
		if not reference_eco_unit_model:
			return self.return_with_error(_("No raster is associated with the reference ecological units specified [%s]" % (self.reference_eco_units)))

		start_year, end_year, error = self.validate_periods()
		
		vector, error = self.get_vector()	
		if error:
			return self.return_with_error(error)

		start_model, end_model, error = self.get_start_and_end_ndvi_raster_models()
		if error:
			return self.return_with_error(error)

		# Extract raster meta data
		meta = get_raster_meta(start_model.rasterfile.name)
		nodata = meta['nodata']
		
		# Clip the raster and save for later referencing
		meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)
	
		"""
		Reproject ndvi_start_raster, ndvi_end_raster and soil_grid_raster based on base_lc_cover raster
		"""
		# reproject soil raster to modis resolution
		reprojected_eco_units_raster_file, nodata = reproject_raster(reference_raster=start_model.rasterfile.name, 
											  raster=reference_eco_unit_model.rasterfile.name,
											  resampling=Resampling.nearest)
		
		# Read reprojected raster
		reference_eco_units_raster, nodata, rastfile = extract_pixels_using_vector(
									reprojected_eco_units_raster_file, 
									vector, nodata)
	
		# Get rasters for the reporting period
		comparison_rasters = self.get_vi_rasters(self.start_year, self.end_year)
		
		datasource = self._do_compute_performance(comparison_rasters, base_rasters=reference_eco_units_raster, nodata=nodata)

		if return_raw:
			return {
				'datasource': datasource,
				'nodata': nodata,
				'resolution': start_model.resolution,
				'meta_path': meta_raster_path
			}
		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="perf", 
			change_enum=PerformanceChangeBinaryEnum, 
			metadata_raster_path=meta_raster_path,  
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=ProductivitySettings.SUB_DIR
		) 

	def _do_compute_performance(self, ndvi_rasters, base_rasters, nodata):
		# Get rasters for the reporting period		
		comparison_rasters = []
		# convert to masked array
		for rast in ndvi_rasters:
			ma_rast = ma.array(rast)
			ma_rast[ma_rast==nodata] = ma.masked
			comparison_rasters.append(ma_rast)

		# comparison_rasters = ndvi_rasters
		reference_eco_units_raster = self.compute_pixel_averages(rasters=base_rasters) #base_rasters		
		
		# compute the per pixel average for rasters in the comparison periods
		mean_ndvi = self.compute_pixel_averages(rasters=comparison_rasters)
		mean_ndvi = ma.array(mean_ndvi) #initialize a masked array


		"""Add the rasters to get units.
		The two rasters are composed of integer values each representing unique 
		property of soil or land cover. As such, a simple addition will give you 
		unique integers for unique combination of land cover and soil properties. 
		For example, the soil raster may have 5 as the integer that represents clay
		soil while the land cover raster may have 10 as the value that represent  
		forest. This implies that a pixel that falls in a forest with clay soil 
		will be represented by a value of 15 in the ecological unit raster! 

		However, for now, this raster will be provided in advance
		"""
		# eco_units = do_raster_operation([base_lc_raster, base_soil_raster], 
		# 								 RasterOperationEnum.ADD, nodata=nodata)

		"""
		Get the frequency distributions of the ecological units
		For each eco unit, get the value of the corresponding pixel
		values from the mean ndvi raster
		"""
		unique_eco_units = self.get_frequency_distribution(reference_eco_units_raster, nodata)

		"""Initialize new array to store max ndvi values"""
		max_ndvi_raster = np.full(comparison_rasters[0].shape, nodata, dtype=float)
		max_ndvi_raster = ma.array(max_ndvi_raster) #initialize a masked array

		"""Remove nodata from eco units"""
		unique_eco_units = [x for x in unique_eco_units if x != nodata]
		for eco in unique_eco_units:			
			"""Get index of matching values"""
			indices = np.where(reference_eco_units_raster==eco)

			"""Extract the corresponding mean ndvi values"""
			# mean_ndvi_vals = np.take(mean_ndvi, indices)
			mean_ndvi_vals = mean_ndvi[tuple(indices)]
			
			# mask nodata values
			mean_ndvi[mean_ndvi==nodata] = ma.masked
			if mean_ndvi_vals.size != 0: #percentile requires an array			
				"""Get the 90th percentile"""
				perc_90 = np.percentile(mean_ndvi_vals, 90) 

				"""Set this 90th percentile value as the value for the matching pixels"""
				# for row, col in zip(indices[0], indices[1]):
				# 	max_ndvi_raster[row, col] = perc_90
				max_ndvi_raster[tuple(indices)] = perc_90
		
		"""Compute mean_ndiv / max_ndvi"""
		max_ndvi_raster[max_ndvi_raster==nodata] = ma.masked

		ratios = do_raster_operation([mean_ndvi, max_ndvi_raster], RasterOperationEnum.DIVIDE, nodata)

		"""If ratio < 0.5, then degraded else stable"""
		df = pd.DataFrame({'ratio': ratios.flatten()})
		df['mapping'] = nodata
		df[np.isnan(df['ratio'])] = nodata
		
		degraded_mask = df['ratio'] < ProductivitySettings.PERFORMANCE_DEGRADED_CUTOFF
		stable_mask = df['ratio'] >= ProductivitySettings.PERFORMANCE_DEGRADED_CUTOFF
		valid_data = df['ratio'] != nodata
		df.loc[degraded_mask & valid_data, ['mapping']] = PerformanceChangeBinaryEnum.DEGRADED.key
		df.loc[stable_mask & valid_data, ['mapping']] = PerformanceChangeBinaryEnum.STABLE.key

		datasource = df['mapping'].values.reshape(ratios.shape)
		datasource = datasource.astype(np.int32)
		
		self.max_ndvi_raster = max_ndvi_raster # just for unit testing purposes
		self.mean_ndvi = mean_ndvi # just for unit testing purposes
		self.ratios = ratios # just for unit testing purposes

		return datasource

	def calculate_productivity(self):
		"""
		Calculate overall Productivity indicator
		Combines Trajectory, State, and Performance sub-indicators
		"""
		self.in_sub_indicator_context = False

		# Clip the raster and save for later referencing
		vector, error = self.get_vector()	
		start_model, error = self.get_vi_raster_model(self.start_year)
		if error:
			return self.return_with_error(self.error)
		meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)
		
		self.error = None
		trajectory = self.calculate_trajectory()
		if self.error:
			return self.return_with_error(self.error)

		self.error = None
		state = self.calculate_state()
		if self.error:
			return self.return_with_error(self.error)
		
		self.error = None
		performance = self.calculate_performance()
		if self.error:
			return self.return_with_error(self.error)

		prod_enum, prod_matrix = self.initialize_productivity_matrix()

		base_file = trajectory['rasterfile']
		traj_array = self.read_raster(trajectory['rasterfile'])
		state_array = self.read_raster(state['rasterfile'])
		perf_array = self.read_raster(performance['rasterfile'])

		# harmonize nodata values
		base_meta = get_raster_meta(self.get_file_path(base_file))
		nodata = base_meta.get('nodata')

		rasters = reshape_rasters([traj_array, state_array, perf_array])
		traj_array = rasters[0]
		state_array = rasters[1]
		perf_array = rasters[2]
 
		df = pd.DataFrame({
						'trajectory': traj_array.flatten(),
						'state': state_array.flatten(),
						'performance': perf_array.flatten()
					})
		df['mapping'] = nodata
		for row in prod_matrix:
			# filter all matching entries as per the matrix
			mask = (df['trajectory'] == row['traj']) & (df['state'] == row['state']) & (df['performance'] == row['perf'])
			df.loc[mask, ['mapping']] = row['mapping']
		
		datasource = df['mapping'].values.reshape(traj_array.shape)
		datasource = datasource.astype(np.int32)

		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="prod", 
			change_enum=prod_enum, 
			metadata_raster_path=meta_raster_path, #start_model.rasterfile.name, 
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=ProductivitySettings.SUB_DIR
		)

	def get_file_path(self, url):
		return get_physical_file_path_from_url(self.request, url)

	def read_raster(self, file):
		return get_raster_values(self.get_file_path(file), 
									band=GenericRasterBandEnum.HAS_SINGLE_BAND, 
									raster_source=self.raster_source, 
									windowed=False)	

	def initialize_productivity_matrix(self):
		"""
		Initialize Productivity change matrix. Return a tuple of (EnumClass, mapping)
		"""
		map_matrix = (None, [])
		if self.compute_version == 1:
			map_matrix = (ProductivityChangeTernaryEnum, [
				{#1
					'traj': TrajectoryChangeTernaryEnum.IMPROVED.key,
					'state': StateChangeTernaryEnum.IMPROVED.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeTernaryEnum.IMPROVED.key
				},
				{#2
					'traj': TrajectoryChangeTernaryEnum.IMPROVED.key,
					'state': StateChangeTernaryEnum.IMPROVED.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeTernaryEnum.IMPROVED.key
				},
				{#3
					'traj': TrajectoryChangeTernaryEnum.IMPROVED.key,
					'state': StateChangeTernaryEnum.STABLE.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeTernaryEnum.IMPROVED.key
				},
				{#4
					'traj': TrajectoryChangeTernaryEnum.IMPROVED.key,
					'state': StateChangeTernaryEnum.STABLE.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeTernaryEnum.IMPROVED.key
				},
				{#5
					'traj': TrajectoryChangeTernaryEnum.IMPROVED.key,
					'state': StateChangeTernaryEnum.DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeTernaryEnum.IMPROVED.key
				},
				{#6
					'traj': TrajectoryChangeTernaryEnum.IMPROVED.key,
					'state': StateChangeTernaryEnum.DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeTernaryEnum.DEGRADED.key
				},
				{#7
					'traj': TrajectoryChangeTernaryEnum.STABLE.key,
					'state': StateChangeTernaryEnum.IMPROVED.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeTernaryEnum.STABLE.key
				},
				{#8
					'traj': TrajectoryChangeTernaryEnum.STABLE.key,
					'state': StateChangeTernaryEnum.IMPROVED.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeTernaryEnum.STABLE.key
				},
				{#9
					'traj': TrajectoryChangeTernaryEnum.STABLE.key,
					'state': StateChangeTernaryEnum.STABLE.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeTernaryEnum.STABLE.key
				},
				{#10
					'traj': TrajectoryChangeTernaryEnum.STABLE.key,
					'state': StateChangeTernaryEnum.STABLE.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeTernaryEnum.DEGRADED.key
				},
				{#11
					'traj': TrajectoryChangeTernaryEnum.STABLE.key,
					'state': StateChangeTernaryEnum.DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeTernaryEnum.DEGRADED.key
				},
				{#12
					'traj': TrajectoryChangeTernaryEnum.STABLE.key,
					'state': StateChangeTernaryEnum.DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeTernaryEnum.DEGRADED.key
				},
				{#13
					'traj': TrajectoryChangeTernaryEnum.DEGRADED.key,
					'state': StateChangeTernaryEnum.IMPROVED.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeTernaryEnum.DEGRADED.key
				},
				{#14
					'traj': TrajectoryChangeTernaryEnum.DEGRADED.key,
					'state': StateChangeTernaryEnum.IMPROVED.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeTernaryEnum.DEGRADED.key
				},
				{#15
					'traj': TrajectoryChangeTernaryEnum.DEGRADED.key,
					'state': StateChangeTernaryEnum.STABLE.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeTernaryEnum.DEGRADED.key
				},
				{#16
					'traj': TrajectoryChangeTernaryEnum.DEGRADED.key,
					'state': StateChangeTernaryEnum.STABLE.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeTernaryEnum.DEGRADED.key
				},
				{#17
					'traj': TrajectoryChangeTernaryEnum.DEGRADED.key,
					'state': StateChangeTernaryEnum.DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeTernaryEnum.DEGRADED.key
				},
				{#18
					'traj': TrajectoryChangeTernaryEnum.DEGRADED.key,
					'state': StateChangeTernaryEnum.DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeTernaryEnum.DEGRADED.key
				},
			])
		else:
			map_matrix = (ProductivityChangeBinaryEnum, [
				{#1
					'traj': TrajectoryChangeBinaryEnum.DEGRADED.key,
					'state': StateChangeBinaryEnum.DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeBinaryEnum.DEGRADED.key
				},
				{#2
					'traj': TrajectoryChangeBinaryEnum.DEGRADED.key,
					'state': StateChangeBinaryEnum.DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeBinaryEnum.DEGRADED.key
				},
				{#3
					'traj': TrajectoryChangeBinaryEnum.DEGRADED.key,
					'state': StateChangeBinaryEnum.NOT_DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeBinaryEnum.DEGRADED.key
				},
				{#4
					'traj': TrajectoryChangeBinaryEnum.DEGRADED.key,
					'state': StateChangeBinaryEnum.NOT_DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeBinaryEnum.DEGRADED.key
				},
				{#5
					'traj': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key,
					'state': StateChangeBinaryEnum.DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeBinaryEnum.DEGRADED.key
				},
				{#6
					'traj': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key,
					'state': StateChangeBinaryEnum.DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeBinaryEnum.NOT_DEGRADED.key
				},
				{#7
					'traj': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key,
					'state': StateChangeBinaryEnum.NOT_DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.DEGRADED.key,
					'mapping': ProductivityChangeBinaryEnum.NOT_DEGRADED.key
				},
				{#8
					'traj': TrajectoryChangeBinaryEnum.NOT_DEGRADED.key,
					'state': StateChangeBinaryEnum.NOT_DEGRADED.key,
					'perf': PerformanceChangeBinaryEnum.STABLE.key,
					'mapping': ProductivityChangeBinaryEnum.NOT_DEGRADED.key
				},			
			])
		return map_matrix

	def get_band_values(self, raster_file, band):
		"""
		Get Raster Model

		Args:
			raster_file (string): Raster file to be read
			band (GenericRasterBandEnum):  Raster band to read 
		"""	
		return self.read_band(rasterfile=raster_file,
								  band=band) 

	def read_band(self, rasterfile, band=None):
		"""
		Read bands in a raster
		Args:
			rasterfile (string): Valid raster file to read
			bands (GenericRasterBandEnum): valid value of GenericRasterBandEnum
		"""
		if not band:
			raise AnalysisParamError(_("You must specify the raster band to read"))
		
		return get_raster_values(rasterfile, 
						band=band, 
						raster_source=self.raster_source)

	def return_with_error(self, error):		
		self.error = error
		return return_with_error(self.request, error)