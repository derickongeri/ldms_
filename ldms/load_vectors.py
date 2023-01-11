import os
from django.contrib.gis import geos
# from .models import ShapeFilePoint
from .models import ShapeFile, Feature, Attribute, AttributeValue
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import GEOSGeometry

from .utils import vector_util
from ldms.tests.test_indicators import ProductivityTest

point_csv = os.path.abspath(os.path.join('ldms', 'data', 'points.csv'))
#  shapefiles_data_dir = '/home/nyaga/app/oss_ldms/backend/ldms/data/shapefiles/'
shapefiles_data_dir = '/home/app/web/ldms/data/shapefiles/'
# shapefiles_data_dir = '/home/sftdev/django-apps/oss-ldms/data/shapefiles/'

tunisia_imported = True
algeria_imported = True
libya_imported = True	
egypt_imported = True
mauritania_imported = False
westernsahara_imported = True

def import_shapefiles_dynamic():
	vector_util.load_shapefile_dynamic(shapefiles_data_dir + 'Libya.shp')
	vector_util.load_shapefile_dynamic(shapefiles_data_dir + 'Tunisia/gadm36_TUN_1.shp')
	vector_util.load_shapefile_dynamic(shapefiles_data_dir + 'Tunisia/gadm36_TUN_2.shp')
	vector_util.load_shapefile_dynamic(shapefiles_data_dir + 'Tunisia/gadm36_TUN_0.shp')

def import_regional_level_shape_files():
	#vector_util.load_regional_admin_shapefile(shapefiles_data_dir + 'Regional/OSS_RegionalShapefile_Dissolved.shp')
	vector_util.load_regional_admin_shapefile(shapefiles_data_dir + 'Regional/OSS_Region.shp')

def import_level_zero_shape_files():
	#Tunisia
	if not tunisia_imported:
		vector_util.load_admin_zero_shapefile(shapefiles_data_dir + 'Tunisia/gadm36_TUN_0.shp')
	#Algeria
	if not algeria_imported:
		vector_util.load_admin_zero_shapefile(shapefiles_data_dir + 'Algeria/gadm36_DZA_0.shp')
	#Libya
	if not libya_imported:
		vector_util.load_admin_zero_shapefile(shapefiles_data_dir + 'Libya/gadm36_LBY_0.shp')
	#Egypt
	if not egypt_imported:
		vector_util.load_admin_zero_shapefile(shapefiles_data_dir + 'Egypt/gadm36_EGY_0.shp')
	#Mauritania
	if not mauritania_imported:
		vector_util.load_admin_zero_shapefile(shapefiles_data_dir + 'Mauritania/gadm36_MRT_0.shp')
	#Western sahara
	if not westernsahara_imported:
		vector_util.load_admin_zero_shapefile(shapefiles_data_dir + 'WesternSahara/gadm36_ESH_0.shp')

def import_level_one_shape_files():
	# Tunisia
	if not tunisia_imported:
		vector_util.load_admin_one_shapefile(shapefiles_data_dir + 'Tunisia/gadm36_TUN_1.shp')
 	# Algeria
	if not algeria_imported:
		vector_util.load_admin_one_shapefile(shapefiles_data_dir + 'Algeria/gadm36_DZA_1.shp')
	#Libya
	if not libya_imported:
		vector_util.load_admin_one_shapefile(shapefiles_data_dir + 'Libya/gadm36_LBY_1.shp')
	#Egypt
	if not egypt_imported:
		vector_util.load_admin_one_shapefile(shapefiles_data_dir + 'Egypt/gadm36_EGY_1.shp')
	#Mauritania
	if not mauritania_imported:
		vector_util.load_admin_one_shapefile(shapefiles_data_dir + 'Mauritania/gadm36_MRT_1.shp')
	#Western sahara
	if not westernsahara_imported:
		vector_util.load_admin_one_shapefile(shapefiles_data_dir + 'WesternSahara/gadm36_ESH_1.shp')

def import_level_two_shape_files():
	# Tunisia
	if not tunisia_imported:
		vector_util.load_admin_two_shapefile(shapefiles_data_dir + 'Tunisia/gadm36_TUN_2.shp')
	# Algeria
	if not algeria_imported:
		vector_util.load_admin_two_shapefile(shapefiles_data_dir + 'Algeria/gadm36_DZA_2.shp')
	#Libya
	if not libya_imported:
		vector_util.load_admin_two_shapefile(shapefiles_data_dir + 'Libya/gadm36_LBY_2.shp')
	#Egypt
	if not egypt_imported:
		vector_util.load_admin_two_shapefile(shapefiles_data_dir + 'Egypt/gadm36_EGY_2.shp')
	#Mauritania
	if not mauritania_imported:
		vector_util.load_admin_two_shapefile(shapefiles_data_dir + 'Mauritania/gadm36_MRT_2.shp')
	#Western sahara
	if not westernsahara_imported:
		vector_util.load_admin_two_shapefile(shapefiles_data_dir + 'WesternSahara/gadm36_ESH_2.shp')

# def point_load(verbose=True):
# 	with open(point_csv) as point_file:
# 		for line in point_file:
# 			name, lon, lat = line.split(',')
# 			name = name.replace("\"", "")
# 			point = f"(%s %s)" % (lon.strip(), lat.strip())
# 			ShapeFilePoint.objects.create(name=name, geom=point)

def clip_raster(level, adminid):
	from ldms.utils.raster_util import (get_raster_values, reproject_raster, clip_raster_to_vector)
	from ldms.models import AdminLevelZero, AdminLevelOne, AdminLevelTwo 

	"""test clipping of raster based on polygon"""
	raster_file = "/home/nyaga/django-apps/oss_ldms/data/MODIS_NDVI-20200918T143515Z-001/MODIS_NDVI/modis_2008.tif"
	if level == 0:
		model = AdminLevelZero.objects.get(id=adminid)
	if level == 1:
		model = AdminLevelOne.objects.get(id=adminid)
	if level == 2:
		model = AdminLevelTwo.objects.get(id=adminid)
	clip_raster_to_vector(vector=model.geom.geojson, raster_file=raster_file)
	"""End test clipping of raster based on polygon"""

def test_productivity():
	prod = ProductivityTest()
	# prod.test_performance_no_missing_data()
	prod.test_performance_with_missing_data()

def run():	
	test_productivity()
	
	# reference_soc = get_raster_values("Reference_soc.tif")
	"""	
	from ldms.analysis.soc import SOC
	from ldms.analysis.soc import ClimaticRegion
	
	soc = SOC(
		admin_level=0,
		shapefile_id = 1,
        custom_vector_coords = None, # custom_coords,
        raster_type = 1,
        start_year=2008,
        end_year=2009,
        transform="area",
		write_to_disk=True,
		climatic_region=ClimaticRegion.TemperateDry,
		reference_soc=3
        # request=request,
	)
	res = soc.calculate_soc()

	"""

	"""
	from ldms.models import Raster
	from ldms.analysis.lulc import LULC
	lulc = LULC(
		admin_level=0,
		shapefile_id = 1,
        custom_vector_coords = None, # custom_coords,
        raster_type = 1,
        start_year=2008,
        end_year=2009,
        transform="area",
		show_change=True
        # request=request,
	)
	res = lulc.calculate_lulc_change(return_no_map=False)
	print (res)
	"""

	# from .utils.file_util import read_image_tiff
	# read_image_tiff()

	# from ldms.utils.raster_util import dummy_save_raster
	# dummy_save_raster()

	"""
	shapefile = "/home/nyaga/django-apps/oss_ldms/backend/ldms/data/shapefiles/Tunisia/gadm36_TUN_0.shp"
	raster = "/home/nyaga/django-apps/oss_ldms/backend/ldms/data/OSS RAST/LC_reclassed/LC_2010.tif"
	raster_model = Raster.objects.all().last()

	from .utils.raster_util import RasterCalcHelper
	hlper = RasterCalcHelper(vector=shapefile,
				rasters=[raster_model],
				raster_type_id=1,
				stats=[],
				is_categorical=True,
				transform="area")
	res = hlper.get_stats()
	print (res)
	"""
