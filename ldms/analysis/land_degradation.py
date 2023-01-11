from ldms.enums import (RasterSourceEnum)
from ldms.analysis.productivity import Productivity, ProductivitySettings
from ldms.analysis.soc import SOC
from ldms.analysis.lulc import LULC
from ldms.enums import (ClimaticRegionEnum, LandDegradationChangeEnum, 
		BinaryLandDegradationChangeEnum,
		ProductivityChangeTernaryEnum, SOCChangeEnum, LulcChangeEnum, RasterCategoryEnum)
from ldms.utils.raster_util import (extract_pixels_using_vector, get_raster_meta, clip_raster_to_vector,
				return_raster_with_stats, get_raster_models)
import pandas as pd
import numpy as np
from ldms.utils.vector_util import get_vector
from ldms import ModelNotExistError, AnalysisParamError
from ldms.utils.common_util import cint, return_with_error
from ldms.utils.raster_util import reshape_raster, reshape_rasters
from django.conf import settings
from django.utils.translation import gettext as _

class LandDegrationSettings:
	OVERRIDE_STABLE = False # Override stable to reflect not-degraded
	SUB_DIR = "" # "degr" # Subdirectory to store rasters for degradation
	OUTPUT_BINARY = True # True # Determine if we only output degraded and Not-degraded

class LandDegradation:
	"""
	Wrapper class for Land Degradation indicators.
	Depends on LULC Change, SOC and Productivity indicators 
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
		self.reference_eco_units = kwargs.get('reference_eco_units', None)
		self.reference_soc = kwargs.get('reference_soc', None)
		self.raster_source = kwargs.get('raster_source', RasterSourceEnum.MODIS)
		self.admin_0 = kwargs.get('admin_0', None)
		self.veg_index = kwargs.get('veg_index', RasterCategoryEnum.NDVI.value)

		self.kwargs = kwargs
			
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
			error = _("Year {0} does not have an associated {0} {2} raster{3}.".format(year, self.veg_index,
							self.raster_source.value, " for the selected country" if self.admin_0 else ""))
			if throw_error:
				raise ModelNotExistError(error)
		return (model, error)

	def calculate_land_degradation(self):
		"""
		Compute land degradation
		"""
		kwargs = self.kwargs
		kwargs['write_to_disk'] = True
		kwargs['climatic_region'] = ClimaticRegionEnum.TemperateDry
		
		# Clip the raster and save for later referencing
		vector, error = self.get_vector()
		start_model, error = self.get_vi_raster_model(self.start_year, throw_error=False)
		meta_raster, meta_raster_path, nodata = clip_raster_to_vector(start_model.rasterfile.name, vector)
		
		soc = SOC(**kwargs)
		soc_res = soc.calculate_soc_change()
		if soc.error:
			return self.return_with_error(soc.error)
		
		lulc = LULC(**kwargs)
		lulc_res = lulc.calculate_lulc_change()
		if lulc.error:
			return self.return_with_error(lulc.error)

		prod = Productivity(**kwargs)
		prod_res = prod.calculate_productivity()
		if prod.error:
			return self.return_with_error(prod.error)

		prod_array = prod.read_raster(prod_res['rasterfile'])
		soc_array = prod.read_raster(soc_res['rasterfile'])
		lulc_array = prod.read_raster(lulc_res['rasterfile'])

		lst = reshape_rasters([prod_array, soc_array, lulc_array])
		prod_array, soc_array, lulc_array = lst[0], lst[1], lst[2]

		self.initialize_degradation_matrix()

		df = pd.DataFrame({
						'productivity': prod_array.flatten(),
						'soc': soc_array.flatten(),
						'lulc': lulc_array.flatten()
					})
		df['mapping'] = nodata

		if LandDegrationSettings.OUTPUT_BINARY:
			# If any of the indicators has degraded, then output degraded else output not-degraded
			degraded_mask = (df['productivity'] == ProductivityChangeTernaryEnum.DEGRADED.key) | (df['soc'] == SOCChangeEnum.DEGRADED.key) | (df['lulc'] == LulcChangeEnum.DEGRADED.key)
			nodata_mask = (df['productivity'] != nodata) & (df['soc'] != nodata) & (df['lulc'] != nodata)
			df.loc[degraded_mask, ['mapping']] = LandDegradationChangeEnum.DEGRADED.key

			# exclude no_data values
			df.loc[~degraded_mask & nodata_mask, ['mapping']] = LandDegradationChangeEnum.IMPROVED.key
		else:
			# Replace values
			for row in self.degradation_matrix:
				# filter all matching entries as per the matrix
				mask = (df['productivity'] == row['prod']) & (df['soc'] == row['soc']) & (df['lulc'] == row['lulc'])
				if row['mapping'] == LandDegradationChangeEnum.STABLE and LandDegrationSettings.OVERRIDE_STABLE:
					df.loc[mask, ['mapping']] = LandDegradationChangeEnum.IMPROVED
				else:
					df.loc[mask, ['mapping']] = row['mapping']
		
		datasource = df['mapping'].values.reshape(prod_array.shape)
		datasource = datasource.astype(np.int32)

		return return_raster_with_stats(
			request=self.request,
			datasource=datasource, 
			prefix="degrad", 
			change_enum=BinaryLandDegradationChangeEnum if LandDegrationSettings.OUTPUT_BINARY else LandDegradationChangeEnum,
			metadata_raster_path=meta_raster_path,
			nodata=nodata, 
			resolution=start_model.resolution,
			start_year=self.start_year,
			end_year=self.end_year,
			subdir=LandDegrationSettings.SUB_DIR 
		)
	
	def get_vector(self):
		return get_vector(admin_level=self.admin_level, 
						  shapefile_id=self.shapefile_id, 
						  custom_vector_coords=self.custom_vector_coords, 
						  admin_0=self.admin_0,
						  request=self.request)

	def return_with_error(self, error):		
		self.error = error
		return return_with_error(self.request, error)

	def initialize_degradation_matrix(self):
		self.degradation_matrix = [
			{#1
				'prod': ProductivityChangeTernaryEnum.IMPROVED.key,
				'soc': LulcChangeEnum.IMPROVED.key,
				'lulc': SOCChangeEnum.IMPROVED.key,
				'mapping': LandDegradationChangeEnum.IMPROVED.key
			},
			{#2
				'prod': ProductivityChangeTernaryEnum.IMPROVED.key,
				'soc': LulcChangeEnum.IMPROVED.key,
				'lulc': SOCChangeEnum.STABLE.key,
				'mapping': LandDegradationChangeEnum.IMPROVED.key
			},
			{#3
				'prod': ProductivityChangeTernaryEnum.IMPROVED.key,
				'soc': LulcChangeEnum.IMPROVED.key,
				'lulc': SOCChangeEnum.DEGRADED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#4
				'prod': ProductivityChangeTernaryEnum.IMPROVED.key,
				'soc': LulcChangeEnum.STABLE.key,
				'lulc': SOCChangeEnum.IMPROVED.key,
				'mapping': LandDegradationChangeEnum.IMPROVED.key
			},
			{#5
				'prod': ProductivityChangeTernaryEnum.IMPROVED.key,
				'soc': LulcChangeEnum.STABLE.key,
				'lulc': SOCChangeEnum.STABLE.key,
				'mapping': LandDegradationChangeEnum.IMPROVED.key
			},
			{#6
				'prod': ProductivityChangeTernaryEnum.IMPROVED.key,
				'soc': LulcChangeEnum.STABLE.key,
				'lulc': SOCChangeEnum.DEGRADED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#7
				'prod': ProductivityChangeTernaryEnum.IMPROVED.key,
				'soc': LulcChangeEnum.DEGRADED.key,
				'lulc': SOCChangeEnum.IMPROVED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#8
				'prod': ProductivityChangeTernaryEnum.IMPROVED.key,
				'soc': LulcChangeEnum.DEGRADED.key,
				'lulc': SOCChangeEnum.STABLE.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#9
				'prod': ProductivityChangeTernaryEnum.IMPROVED.key,
				'soc': LulcChangeEnum.DEGRADED.key,
				'lulc': SOCChangeEnum.DEGRADED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#10
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.IMPROVED.key,
				'lulc': SOCChangeEnum.IMPROVED.key,
				'mapping': LandDegradationChangeEnum.IMPROVED.key
			},
			{#11
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.IMPROVED.key,
				'lulc': SOCChangeEnum.STABLE.key,
				'mapping': LandDegradationChangeEnum.IMPROVED.key
			},
			{#12
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.IMPROVED.key,
				'lulc': SOCChangeEnum.DEGRADED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#13
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.STABLE.key,
				'lulc': SOCChangeEnum.IMPROVED.key,
				'mapping': LandDegradationChangeEnum.IMPROVED.key
			},
			{#14
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.STABLE.key,
				'lulc': SOCChangeEnum.STABLE.key,
				'mapping': LandDegradationChangeEnum.STABLE.key
			},
			{#15
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.STABLE.key,
				'lulc': SOCChangeEnum.DEGRADED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#16
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.DEGRADED.key,
				'lulc': SOCChangeEnum.IMPROVED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#17
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.DEGRADED.key,
				'lulc': SOCChangeEnum.STABLE.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#18
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.DEGRADED.key,
				'lulc': SOCChangeEnum.DEGRADED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},

			{#19
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.IMPROVED.key,
				'lulc': SOCChangeEnum.IMPROVED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#20
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.IMPROVED.key,
				'lulc': SOCChangeEnum.STABLE.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#21
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.IMPROVED.key,
				'lulc': SOCChangeEnum.DEGRADED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#22
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.STABLE.key,
				'lulc': SOCChangeEnum.IMPROVED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#23
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.STABLE.key,
				'lulc': SOCChangeEnum.STABLE.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#24
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.STABLE.key,
				'lulc': SOCChangeEnum.DEGRADED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#25
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.DEGRADED.key,
				'lulc': SOCChangeEnum.IMPROVED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#26
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.DEGRADED.key,
				'lulc': SOCChangeEnum.STABLE.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
			{#27
				'prod': ProductivityChangeTernaryEnum.STABLE.key,
				'soc': LulcChangeEnum.DEGRADED.key,
				'lulc': SOCChangeEnum.DEGRADED.key,
				'mapping': LandDegradationChangeEnum.DEGRADED.key
			},
		]
