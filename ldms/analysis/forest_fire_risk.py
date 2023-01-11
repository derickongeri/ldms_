from ldms.analysis.gee import GEE
from ldms.enums import RasterSourceEnum
from ldms.utils.common_util import (validate_years, return_with_error,
	 cint, parse_date, format_date, validate_dates)
import ee
import datetime
from django.utils.translation import gettext as _
from ldms.utils.vector_util import get_vector, get_vector_from_db
import json
from ee.ee_exception import EEException 
from ldms.analysis.gee_scripts import forest_risk_assessment
from ldms.models import RegionalAdminLevel
from ldms.utils.settings_util import get_settings 
from ldms.utils import log_util
from ldms.models import AdminLevelZero
from ldms.utils.file_util import download_file, get_download_url, unzip_file, get_absolute_media_path, copy_file

class ForestFireRiskSettings:
	SUB_DIR = "" # "forestloss" # Subdirectory to store rasters for forestloss
	DEFAULT_SCALE = 1000

class ForestFireRiskGEE(GEE):
	"""
	Class to auto-run scripts to detect Forest Fire on GEE 
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
			**start_date (date)**: 
				Analysis start date. 
			**end_date (date)**: 
				Analysis end date. 
			**raster_source (string)**: 
				Either Sentinel-2 or Landsat
			**country_name (string)**: 
				Country Name 
			**request**:
				WebRequest 
		"""
		self.admin_level = kwargs.get('admin_level', None)
		self.shapefile_id = kwargs.get('shapefile_id', None)
		self.custom_vector_coords = kwargs.get('custom_vector_coords', None)
		self.admin_0 = kwargs.get('admin_0', None)

		# Set start and end dates of a period BEFORE the fire. Make sure it is long enough for 
		# Sentinel-2 to acquire an image (repetition rate = 5 days). Adjust these parameters, if
		# your ImageCollections (see Console) do not contain any elements.
		self.start_date = kwargs.get('start_date', None) # '2017-02-20'
		self.end_date = kwargs.get('end_date', None) # '2017-03-28'

		self.platform = kwargs.get('raster_source', RasterSourceEnum.SENTINEL2)# "L8"
		self.error = "" 
		self.request = kwargs.get('request', None)
		self.country_name = kwargs.get('country_name', None)
		self.geometry = None
	
	def get_country(self):
		vector_model = AdminLevelZero.objects.filter(id=self.admin_0).first()
		return vector_model, "The admin_0 value of {} specified does not exist".format(self.admin_0) if not vector_model else None

	def calculate_fire_risk(self):
		"""Calculate forest fire risk 
		"""
		self.start_date = parse_date(self.start_date)
		self.end_date = parse_date(self.end_date) 

		self.start_date, self.end_date, period_error = self.validate_periods()
		if period_error:
			return self.return_with_error(period_error)
		
		# validate vector
		vector, error = self.get_country_vector() # self.get_vector()
		if error:
			return self.return_with_error(error)

		# regional_vector, error = self.get_regional_vector()
		# if error:
		# 	return self.return_with_error(error)
		
		super(ForestFireRiskGEE, self).initialize()
		#self.geometry = ee.Geometry.Polygon(json.loads(vector)['coordinates'][0])
		self.geometry = ee.Geometry(json.loads(vector))
		# self.roi = ee.Geometry(json.loads(regional_vector))
		# self.set_platform(self.platform)
		# self.filter_rasters()

		country_vect, error = self.get_country()
		if error:
			return self.return_with_error(error)

		forest_risk_assessment.entrypoint(
					#roi=ee.Geometry.Polygon(json.loads(regional_vector)['coordinates'][0]),
					# roi=self.roi,
					aoi=self.geometry,
					country_name=country_vect.name_0,
					analysis_start=format_date(self.start_date), 
					analysis_end=format_date(self.end_date), 
					scale=ForestFireRiskSettings.DEFAULT_SCALE #get_settings().alert_scale
				)
		
		results = forest_risk_assessment.get_results()
		for res in results: #is of type [[x, [], []]]
			merged_tiff = res[0]
			daily_tiffs = res[1]
			daily_stats = res[2]
			# get stats on daily tiff

		fl = self.download_file(merged_tiff)
		# copy file from temp to media dir
		dest = get_absolute_media_path(file_path=None, 
										is_random_file=True, 
										random_file_prefix="firerisk",
										random_file_ext=".tif")
		out_file = copy_file(fl, dest)
		url = get_download_url(self.request, out_file.split("/")[-1])
		self.results = results	
		stats_obj = {
			"start": format_date(self.start_date),
			"end": format_date(self.end_date),
			"scale": ForestFireRiskSettings.DEFAULT_SCALE,
			"rasterfile": str(url),
			"nodata": 0, # None, # nodata_count * (resolution or 1),
			'stats': daily_stats,
		} 
		return stats_obj

	def download_file(self, url):
		"""
		Download file from the returned url
		"""
		dest_file = self.generate_file_name()
		fl = download_file(url, dest_file)
		return unzip_file(file_path=fl, 
				use_temp_dir=True, 
				dest_dir=".", 
				return_full_path=True
			)[0]

	def generate_file_name(self):
		"""
		Generate random file name with a .zip extension
		"""
		out_file = get_absolute_media_path(file_path=None, 
									is_random_file=True, 
									random_file_prefix="firerisk",
									random_file_ext=".zip",
									sub_dir=None,
									use_static_dir=False)
		return out_file

	def validate_periods(self):
		"""
		Validate the start and end dates

		Returns:
			tuple (start_date, end_date, error)
		"""		
		start_date, end_date, error = validate_dates(
						start_date=self.start_date,
						end_date=self.end_date,
						both_valid=True)
		return (start_date, end_date, error)

	def get_vector(self):
		return get_vector(admin_level=self.admin_level, 
						  shapefile_id=self.shapefile_id, 
						  custom_vector_coords=self.custom_vector_coords, 
						  admin_0=None,
						  request=self.request)

	def get_country_vector(self):
		return get_vector(admin_level=0, 
						  admin_0=self.admin_0,
						  shapefile_id=self.admin_0, 
						  custom_vector_coords=None, #self.custom_vector_coords, 
						  request=self.request)
	
	def get_regional_vector(self):
		return get_vector(admin_level=-1, 
						  shapefile_id=RegionalAdminLevel.objects.first().id,
						  custom_vector_coords=self.custom_vector_coords, 
						  admin_0=None,
						  request=self.request)

	def return_with_error(self, error):		
		self.error = error
		return return_with_error(self.request, error)