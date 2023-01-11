
from django.utils.translation import gettext as _
from ldms.analysis.lulc import LULC
from ldms.enums import RasterSourceEnum
import ee
from ldms.utils.vector_util import get_vector
from ldms.analysis.gee import GEE
from ldms.enums import (ForestChangeEnum, ForestChangeEnum, LCEnum, GenericRasterBandEnum,
	 RasterSourceEnum, RasterCategoryEnum)
from ldms.utils.common_util import cint, flt, return_with_error, validate_years
from ldms.utils.file_util import get_absolute_media_path, get_download_url, get_media_dir, file_exists
from ldms.utils.raster_util import (get_raster_values, get_raster_object, 
								save_raster, get_raster_meta, reproject_raster,
								extract_pixels_using_vector, clip_raster_to_vector,
								return_raster_with_stats, get_raster_models)
from ldms.utils.raster_util import RasterCalcHelper
from django.conf import settings
import numpy as np

class ForestChangeSettings:
	SUB_DIR = "" # "forestloss" # Subdirectory to store rasters for forestloss
	RASTER_BASE_YEAR = 2000

class ForestChange:
	"""
	Wrapper class for calculating ForestChange
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
		self.analysis_year = kwargs.get('end_year', None)
		self.transform = kwargs.get('transform', "area")
		self.request = kwargs.get('request', None)
		self.error = None
		self.analysis_type = None #one of LULC or LULC_CHANGE
		self.raster_source = kwargs.get('raster_source', RasterSourceEnum.LULC)
		self.enforce_single_year = True
		self.admin_0 = kwargs.get('admin_0', None)
		
		self.lulc = LULC(
			admin_0=self.admin_0,
			admin_level=self.admin_level,
			shapefile_id = self.shapefile_id,
			custom_vector_coords = self.custom_vector_coords,
			raster_type = self.raster_type,
			start_year=self.start_year,
			end_year=self.end_year,
			transform=self.transform,
			raster_source=self.raster_source,
			enforce_single_year=False,
			request=self.request,
		)

	def calculate_forest_change(self):	
		if self.raster_source == RasterSourceEnum.HANSEN:
			return self.calculate_loss_based_on_hansen()
		return self.calculate_change_based_on_lulc()		

	def calculate_change_based_on_lulc(self):
		"""Compute Forest Change by getting the LULC values for Forest cover"""
		res = self.lulc.calculate_lulc()
		self.error = self.lulc.error
		return res

	def calculate_loss_based_on_hansen(self):
		"""
		Compute Forest Change using local hansen data
		
		Returns:
			[Response]: [A JSON string with statistic values]
		"""    
		if not self.analysis_year:
			self.analysis_year = cint(self.end_year)

		self.analysis_type = ForestChangeEnum.FOREST_LOSS
		"""Default the year to ForestChangeSettings.RASTER_BASE_YEAR because Hansen
		is a single raster containing values for all the years. 
		See https://gitlab.com/locateit/oss-land-degradation-monitoring-service/oss-ldms/-/issues/22
		"""
		
		self.start_year = ForestChangeSettings.RASTER_BASE_YEAR # self.start_year
		self.end_year = ForestChangeSettings.RASTER_BASE_YEAR # self.end_year
		start_year = self.start_year
		end_year = self.end_year

		vector_id = self.shapefile_id
		admin_level = self.admin_level
		raster_type = self.raster_type
				
		custom_coords = self.custom_vector_coords
		transform = self.transform
		
		"""
		- If user has drawn custom polygon, ignore the vector id
		since the custom polygon could span several shapefiles.
		- If no custom polygon is selected, demand an admin_level 
		and the vector id
		"""
		vector, error = get_vector(admin_level=self.admin_level, shapefile_id=self.shapefile_id, 
						custom_vector_coords=self.custom_vector_coords, admin_0=None,
						request=self.request)
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
				return self.return_with_error(_("Forest change can only be analysed for a single period"))

		if cint(self.analysis_year) < ForestChangeSettings.RASTER_BASE_YEAR:
			return self.return_with_error(_("Forest change can only be analysed from year {0} onwards".format(ForestChangeSettings.RASTER_BASE_YEAR)))

		# Get Raster Models	by period and raster type
		# Do not filter by year since Hansen is a single raster with pixel values being the years
		raster_models = get_raster_models(
						admin_zero_id=self.admin_0,
						raster_category=RasterCategoryEnum.FOREST_LOSS.value,
						raster_source=self.raster_source.value,
						raster_year=ForestChangeSettings.RASTER_BASE_YEAR
					)

		if not raster_models:
			return self.return_with_error(_("No matching rasters"))

		if self.enforce_single_year:
			if len(raster_models) > 1:
				return self.return_with_error(_("Multiple Hansen rasters exist for the selected period"))

		lulc_raster_path = None
		for raster_model in raster_models:			
			# for raster_model in raster_models:
			raster_path = get_media_dir() + raster_model.rasterfile.name

			# Validate existence of the raster file
			if not file_exists(raster_path):
				return self.return_with_error(_("Raster %s does not exist" % (raster_model.rasterfile.name)))

			if raster_model.raster_year == start_year:
				lulc_raster, lulc_raster_path, nodata = clip_raster_to_vector(raster_model.rasterfile.name, vector)
			
		if not lulc_raster_path:
			return self.return_with_error(_("No matching raster for year %s" % (start_year)))

		hlper = RasterCalcHelper(vector=vector,
					rasters=raster_models,
					raster_type_id=raster_type,
					stats=[],
					is_categorical=True,
					transform=transform)
		res = hlper.get_stats()

		datasource = lulc_raster[0] # since its a (1, width, height) matrix
		
		"""For all the other years, replace their values with nodata value"""
		if self.analysis_year:
			val = flt(self.analysis_year - ForestChangeSettings.RASTER_BASE_YEAR)
			datasource = np.where(datasource != val, nodata, datasource)

		return return_raster_with_stats(
			request=self.request,
			datasource=datasource,
			prefix="forestloss", 
			change_enum=ForestChangeEnum, 
			metadata_raster_path=lulc_raster_path, 
			nodata=nodata, 
			resolution=raster_model.resolution,
			start_year=start_year,
			end_year=end_year,
			subdir=ForestChangeSettings.SUB_DIR,
			results=res
		)
	
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
							both_valid=False)

# class ForestChangeGEE(GEE):
# 	"""
# 	Wrapper for computing forest change based on GEE
# 	"""
# 	def __init__(self, year, geometry):
# 		self.year = year
# 		self.geometry = geometry
		
# 	def compute(self):
# 		super(ForestChangeGEE, self).initialize()
# 		self.geometry = ee.Geometry.Polygon([ [ [ -72.435883, -35.540058 ], [ -72.431499, -35.544763 ], [ -72.426375, -35.544077 ], [ -72.424671, -35.539961 ], [ -72.423897, -35.533738 ], [ -72.427985, -35.534038 ], [ -72.431896, -35.530179 ], [ -72.437491, -35.53002 ], [ -72.440437, -35.527437 ], [ -72.444927, -35.525227 ], [ -72.444293, -35.522331 ], [ -72.433256, -35.514318 ], [ -72.424906, -35.509559 ], [ -72.414699, -35.509016 ], [ -72.407876, -35.504213 ], [ -72.402089, -35.499796 ], [ -72.394356, -35.497516 ], [ -72.389394, -35.488496 ], [ -72.382101, -35.484537 ], [ -72.376473, -35.483862 ], [ -72.370793, -35.481939 ], [ -72.365708, -35.482081 ], [ -72.353893, -35.479495 ], [ -72.344741, -35.47975 ], [ -72.341638, -35.478587 ], [ -72.332675, -35.483415 ], [ -72.320215, -35.477513 ], [ -72.316775, -35.480522 ], [ -72.306029, -35.479152 ], [ -72.301453, -35.479277 ], [ -72.293792, -35.478654 ], [ -72.251728, -35.508528 ], [ -72.248369, -35.513615 ], [ -72.247737, -35.523209 ], [ -72.248498, -35.529435 ], [ -72.246188, -35.535326 ], [ -72.245506, -35.543673 ], [ -72.243163, -35.548733 ], [ -72.231825, -35.558198 ], [ -72.23094, -35.561553 ], [ -72.226918, -35.56291 ], [ -72.227561, -35.566224 ], [ -72.223113, -35.569674 ], [ -72.22323, -35.572586 ], [ -72.22343, -35.577577 ], [ -72.226209, -35.583332 ], [ -72.221184, -35.585133 ], [ -72.214532, -35.584478 ], [ -72.209506, -35.586277 ], [ -72.209606, -35.588773 ], [ -72.203545, -35.590184 ], [ -72.200097, -35.59319 ], [ -72.194214, -35.586267 ], [ -72.193014, -35.581719 ], [ -72.18613, -35.575239 ], [ -72.17897, -35.574595 ], [ -72.16969, -35.584834 ], [ -72.173583, -35.593059 ], [ -72.176048, -35.60382 ], [ -72.18497, -35.610247 ], [ -72.187715, -35.615171 ], [ -72.184774, -35.618164 ], [ -72.181208, -35.618258 ], [ -72.175342, -35.624659 ], [ -72.169229, -35.62482 ], [ -72.167881, -35.629436 ], [ -72.159844, -35.632562 ], [ -72.153286, -35.6344 ], [ -72.150229, -35.63448 ], [ -72.146939, -35.641645 ], [ -72.146132, -35.647079 ], [ -72.141742, -35.652191 ], [ -72.138321, -35.656028 ], [ -72.13812, -35.663945 ], [ -72.126176, -35.645517 ], [ -72.092, -35.645568 ], [ -72.085535, -35.649898 ], [ -72.084659, -35.653668 ], [ -72.084836, -35.658244 ], [ -72.078497, -35.665902 ], [ -72.081174, -35.669165 ], [ -72.083835, -35.672011 ], [ -72.033842, -35.67245 ], [ -72.037521, -35.675272 ], [ -72.039224, -35.679809 ], [ -72.038951, -35.686062 ], [ -72.041117, -35.689339 ], [ -72.042773, -35.692628 ], [ -72.0429, -35.695957 ], [ -72.047138, -35.700013 ], [ -72.050309, -35.702848 ], [ -72.055409, -35.702718 ], [ -72.058533, -35.704305 ], [ -72.061147, -35.705904 ], [ -72.059218, -35.708868 ], [ -72.065651, -35.711351 ], [ -72.067506, -35.712413 ], [ -72.071994, -35.711189 ], [ -72.073439, -35.713371 ], [ -72.077573, -35.714745 ], [ -72.079938, -35.717273 ], [ -72.082713, -35.718682 ], [ -72.087216, -35.717826 ], [ -72.091747, -35.71771 ], [ -72.095061, -35.721323 ], [ -72.099053, -35.719001 ], [ -72.101843, -35.720779 ], [ -72.103117, -35.718527 ], [ -72.108935, -35.716527 ], [ -72.112603, -35.717542 ], [ -72.114314, -35.714908 ], [ -72.118672, -35.710357 ], [ -72.122224, -35.708415 ], [ -72.128817, -35.703066 ], [ -72.133713, -35.700719 ], [ -72.138228, -35.700231 ], [ -72.141939, -35.702354 ], [ -72.143005, -35.706394 ], [ -72.146219, -35.70742 ], [ -72.145853, -35.709649 ], [ -72.150909, -35.711366 ], [ -72.155965, -35.713082 ], [ -72.161898, -35.714036 ], [ -72.166531, -35.716503 ], [ -72.175577, -35.715895 ], [ -72.183909, -35.720113 ], [ -72.191113, -35.718812 ], [ -72.197382, -35.716796 ], [ -72.201459, -35.716688 ], [ -72.204267, -35.718832 ], [ -72.202543, -35.721097 ], [ -72.204414, -35.722527 ], [ -72.222641, -35.724629 ], [ -72.227261, -35.726724 ], [ -72.235083, -35.729473 ], [ -72.238932, -35.734917 ], [ -72.24067, -35.733021 ], [ -72.245489, -35.728822 ], [ -72.249357, -35.72354 ], [ -72.25428, -35.721927 ], [ -72.252846, -35.720117 ], [ -72.253193, -35.717518 ], [ -72.253028, -35.713454 ], [ -72.254297, -35.711201 ], [ -72.259189, -35.708849 ], [ -72.260352, -35.704009 ], [ -72.26704, -35.701239 ], [ -72.269079, -35.695636 ], [ -72.272158, -35.693333 ], [ -72.276672, -35.69284 ], [ -72.281246, -35.693825 ], [ -72.286258, -35.694428 ], [ -72.289096, -35.697309 ], [ -72.296826, -35.697837 ], [ -72.299889, -35.695164 ], [ -72.303904, -35.693574 ], [ -72.30712, -35.694595 ], [ -72.310712, -35.693757 ], [ -72.314619, -35.689581 ], [ -72.31495, -35.686613 ], [ -72.317015, -35.681748 ], [ -72.32, -35.677227 ], [ -72.322548, -35.673089 ], [ -72.32735, -35.674682 ], [ -72.33262, -35.6787 ], [ -72.339437, -35.683091 ], [ -72.34615, -35.684986 ], [ -72.349331, -35.687812 ], [ -72.355587, -35.690969 ], [ -72.362742, -35.691185 ], [ -72.366785, -35.69024 ], [ -72.371548, -35.69427 ], [ -72.375996, -35.690814 ], [ -72.383994, -35.686842 ], [ -72.391534, -35.684131 ], [ -72.394996, -35.681535 ], [ -72.398494, -35.679771 ], [ -72.403081, -35.679641 ], [ -72.409038, -35.675725 ], [ -72.411586, -35.675653 ], [ -72.418087, -35.672554 ], [ -72.421583, -35.670789 ], [ -72.426063, -35.668163 ], [ -72.428451, -35.664348 ], [ -72.435916, -35.659971 ], [ -72.437177, -35.65369 ], [ -72.438983, -35.648225 ], [ -72.444623, -35.648897 ], [ -72.45003, -35.644162 ], [ -72.453614, -35.644475 ], [ -72.458199, -35.644344 ], [ -72.460111, -35.641374 ], [ -72.45944, -35.637646 ], [ -72.454293, -35.636545 ], [ -72.450834, -35.639142 ], [ -72.447617, -35.635487 ], [ -72.444069, -35.636005 ], [ -72.44247, -35.634386 ], [ -72.446366, -35.63011 ], [ -72.443712, -35.627688 ], [ -72.450503, -35.619583 ], [ -72.450413, -35.617503 ], [ -72.437995, -35.613279 ], [ -72.43729, -35.608719 ], [ -72.432582, -35.605939 ], [ -72.441554, -35.57737 ], [ -72.437778, -35.572481 ], [ -72.437582, -35.567907 ], [ -72.436315, -35.562114 ], [ -72.437558, -35.555416 ], [ -72.437362, -35.550842 ], [ -72.435007, -35.543414 ], [ -72.435883, -35.540058 ] ] ]);
# 		# img = ee.Image('UMD/hansen/global_forest_change_%s'.format(self.year))
# 		img = ee.Image('LANDSAT/LT05/C01/T1_SR/LT05_034033_20000913')
# 		area = ee.FeatureCollection(self.geometry)
# 		# images = ee.ImageCollection(img)

# 		# Print image object WITH call to getInfo(); prints image metadata.
# 		print(img.getInfo())
