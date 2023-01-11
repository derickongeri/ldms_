import os
from django.contrib.gis import geos
# from .models import ShapeFilePoint
from ldms.models import (RegionalAdminLevel, AdminLevelZero, AdminLevelOne, 
				AdminLevelTwo, ComputationThreshold, CustomShapeFile)
from ldms.models import ShapeFile, Feature, Attribute, AttributeValue
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import GEOSGeometry, GeometryCollection
from django.contrib.gis.gdal.field import \
    OFTDate, OFTDateTime, OFTInteger, OFTReal, OFTString, OFTTime

from rest_framework import serializers
from django.contrib.gis.utils import LayerMapping
from django.db.models.signals import pre_save
import json
from django.utils.translation import gettext as _
import shapely.geometry 
import pyproj
from shapely.geometry import shape
from shapely.ops import transform
from functools import partial
from ldms.utils.settings_util import get_settings
import geopandas as gpd
from django.contrib.auth import get_user_model

import fiona
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union		
import zipfile
import shutil
import tempfile
import logging

log = logging.getLogger(f'ldms.apps.{__name__}')


User = get_user_model()

def load_shapefile_dynamic(shape_file_path=None, verbose=True):
	"""
	Read a shapefile and persist the details in the database
	Refer to https://django.readthedocs.io/en/1.5.x/ref/contrib/gis/gdal.html
	"""
	shape_file_path = shape_file_path
	
	### Load the shapefile
	ds = DataSource(shape_file_path)
	
	print(len(ds)) # or ds.layer_count check number of layers. Shapefiles can only have one layer 
	layer = ds[0] # get first layer
	print (layer)

	geometry_type = layer.geom_type.name # get the geometry type
	feature_count = len(layer) # Get the number of features contained by the layer
	srs = layer.srs # a layer may have a spatial reference system
	projection = None # PROJ.4 representation
	if srs:
		projection = srs.proj4 
		srs = srs.name
	
	attribute_fields = layer.fields # shapefiles also support attribute fields that may contain additional data
	#field_types = [fld.__name__ for fld in lyr.field_types] examine the OGR types (e.g. integer or string) associated with each of the fields

	'''
	Iterate over each feature in the layer and extract info
	from both the feature's geometry (accessible using the geom attribute) 
	as well as the feature's attribute fields (whole values are accessible
	via the get() method)
	'''
	# for feat in layer:
	# 	print (feat.get('NAME'), feat.geom.num_points)

	first_two_features = layer[0:2] #layers may be sliced

	'''Boundary geometries may be exported as WKT or GeoJSON'''
	# feat = layer[0]
	# geom = feat.geom
	# print(geom.wkt) #export to WKT
	# print(geom.json) #export to JSON
	# print(geom.geojson) #export to GeoJSON
	# print(geom.wkb) # WKB (as Python binary buffer)
	
	# Create Shapefile
	shape_file = ShapeFile.objects.create(
		filename = layer.name, 
		srs = srs or "",
		geom_type = geometry_type, 
		encoding = ""
	)
	
	first_feature = layer[0]
	# Create attributes
	for field, field_type, width, precision in zip(layer.fields, layer.field_types, layer.field_widths, layer.field_precisions):
		attrib = Attribute.objects.create(
			shapefile = shape_file,
			name = field,
			type = first_feature[field].type,
			width = width,
			precision = precision
		)

	# Create features 
	# for geom in layer.get_geoms():
	for i, feat in enumerate(layer):
		geom = feat.geom # geom is now an ogr geometry object
		geometry = GEOSGeometry(geom.geojson)
		geometry_type = geom.geom_type.name

		feature = Feature.objects.create(
			feature_name = "Feature %s" % (i+1),
			shapefile = shape_file,
			# geom_point = geometry if geometry_type == 'Point' else None,
			# geom_multipoint = geometry if geometry_type == 'MultiPoint' else None,
			# geom_linestring = geometry if geometry_type == 'LineString' else None,
			# geom_multilinestring = geometry if geometry_type == 'MultiLineString' else None,
			# geom_polygon = geometry if geometry_type == 'Polygon' else None,
			# geom_multipolygon = geometry if geometry_type == 'MultiPolygon' else None,
			# geom_geometrycollection = geometry if geometry_type == 'GeometryCollection' else None,
			geom_geometrycollection = GeometryCollection(geometry)
		)

		# Create attribute values for the selected feature		
		for field in layer.fields:
			attrib = Attribute.objects.get(shapefile_id=shape_file.id, name=field)
			AttributeValue.objects.create(
				feature = feature,
				attribute = attrib,
				value = feat.get(field)
			)

def read_shapefile(file_path):
	"""
	Read shapefile into Geo object
	"""

	def read_polygons(fpath):
		"""
		Use this when shapefile contains only polygons
		"""
		multi = []
		# append the geometries to the list
		for pol in fiona.open(fpath):
			multi.append(shape(pol['geometry']))

		# create the MultiPolygon from the list of Polygons
		multi = MultiPolygon(multi)
		print (multi.wkt)
		# 'MULTIPOLYGON (((249744.2315302934148349 142798.1643468967231456, 250113.7910872535139788 142132.9571443685272243, ..., 249870.8182051893090829 142570.3083320840960369)))'
		return multi.wkt

	def read_shapes(fpath):
		"""
		Use this when shapefile contains shapes of different types
		"""
		geoms =[shape(feature['geometry']) for feature in fiona.open(fpath)]
		result = unary_union(geoms) 
		# MULTIPOLYGON (((0.00 0.00, 1.00 1.00, 1.00 0.00, 0.00 0.00)), ((1.00 1.00, 2.00 2.00, 2.00 0.00, 1.0 1.00)))
		return result
	
	from ldms.utils.file_util import (file_exists, get_absolute_media_path)
	
	objs = None
	fp = get_absolute_media_path(file_path)	
	if file_exists(fp):
		# Open and extract zipfile
		try:
			tmpdir = tempfile.mkdtemp()
			zf = zipfile.ZipFile(fp)
			zf.extractall(tmpdir)
			# read shapefile
			for i, file in enumerate(os.listdir(tmpdir)):
				if file.endswith(".shp"):
					geoms = read_polygons(os.path.join(tmpdir, file))
					# geoms2 = read_shapes(fp)
					objs = GeometryCollection(GEOSGeometry(geoms))
		except Exception as e:
			shutil.rmtree(tmpdir)
			log.log(logging.ERROR, 'Error: Could not open zipfile.' + str(e))
		finally:
			# Remove tempdir with unzipped shapefile
			shutil.rmtree(tmpdir)
	
	return objs
	# 	CustomShapeFile.objects.create(
	# 		owner = User.objects.get(email='admin@admin.com'),
	# 		name = "test name",
	# 		# description = models.TextField(_("Description of the vector"), blank=False)
	# 		# file = models.FileField(_("Upload Shapefile"))
	# 		#shape_length = models.FloatField(blank=True, null=True, default=0)
	# 		# shape_area = models.FloatField(blank=True, null=True, default=0)	
	# 		geom = GeometryCollection(GEOSGeometry(geoms))
	# 		# objects = GeoManager() #to allow for spatial queries and operations
	# 	)

	# 	# data = gpd.read_file(fp)
	# 	# CustomShapeFile.objects.create(
	# 	# 	owner = User.objects.get(email='admin@admin.com'),
	# 	# 	name = "test name",
	# 	# 	# description = models.TextField(_("Description of the vector"), blank=False)
	# 	# 	# file = models.FileField(_("Upload Shapefile"))
	# 	# 	#shape_length = models.FloatField(blank=True, null=True, default=0)
	# 	# 	# shape_area = models.FloatField(blank=True, null=True, default=0)	
	# 	# 	geom = data.to_json()
	# 	# 	# objects = GeoManager() #to allow for spatial queries and operations
	# 	# )
	# return None

def delete_shapefile(shape_file_path):
	"""	
	Delete a shapefile and the associated data
	TODO: Implement this
	"""
	pass

def verify_shapefile(shape_file_path):
	"""
	Validate that the shapefile is a valid shapefile 
	because users can lie about the file formats
	TODO: Implement this
	"""
	pass

def load_regional_admin_shapefile(shape_file_path):
	"""Load regional admin shapefile

	Args:
		shape_file_path ([string]): Absolute path of the shapefile
	"""
	# mapping = {
	# 	'asap0_id': 'asap0_id',
	# 	'name0': 'name0',
	# 	'name0_shr': 'name0_shr',	
	# 	'asap_cntry': 'asap_cntry',
	# 	'an_crop': 'an_crop',
	# 	'an_range': 'an_range',
	# 	'km2_tot': 'km2_tot',	
	# 	'km2_crop': 'km2_crop',
	# 	'km2_rang2': 'km2_rang2',
	# 	'g1_units': 'g1_units',	
	# 	'isocode': 'isocode',
	# 	'name': 'NAME',
	# 	'geom': 'MULTIPOLYGON'
	# }
	mapping = {
		"object_id": "OBJECTID",
		"shape_length": "Shape_Leng",
		"shape_area": "Shape_Area",
		"geom": "MULTIPOLYGON"
	} 
	do_import(RegionalAdminLevel, shape_file_path, mapping)

def load_admin_zero_shapefile(shape_file_path):
	"""Load admin zero shapefile

	Args:
		shape_file_path ([string]): Absolute path of the shapefile
	"""
	mapping = {
		'gid_0': 'GID_0',
		'name_0': 'NAME_0',
		# 'cpu': 'CPU',
		'geom': 'MULTIPOLYGON'
	}
	do_import(AdminLevelZero, shape_file_path, mapping)

def load_admin_one_shapefile(shape_file_path):
	"""Load admin one shapefile 

	Args:
		shape_file_path ([string]): Absolute path of the shapefile
	"""
	mapping = {
		# 'admin_zero': {'admin_zero_id': 'admin_zero_id'}, # foreign key field
		'gid_0': 'GID_0',
		'name_0': 'NAME_0',
	    'gid_1': 'GID_1',
		'name_1': 'NAME_1',	
		'varname_1': 'VARNAME_1',	
		'nl_name_1': 'NL_NAME_1',	
	 	'type_1': 'TYPE_1',	
		'engtype_1': 'ENGTYPE_1',	
		'cc_1': 'CC_1',
	    'hasc_1': 'HASC_1',	
		# 'cpu': 'CPU',
		'geom': 'MULTIPOLYGON'
	}
	do_import(AdminLevelOne, shape_file_path, mapping)

def load_admin_two_shapefile(shape_file_path):
	"""Load admin two shapefile 
	Args:
		shape_file_path ([string]): Absolute path of the shapefile
	"""
	mapping = {
		'gid_0': 'GID_0',
		'name_0': 'NAME_0',
		'gid_1': 'GID_1',
		'name_1': 'NAME_1',
		'nl_name_1': 'NL_NAME_1',
		'gid_2': 'GID_2',
		'name_2': 'NAME_2',
		'varname_2': 'VARNAME_2',
		'nl_name_2': 'NL_NAME_2',
		'type_2': 'TYPE_2',
		'engtype_2': 'ENGTYPE_2',
		'cc_2': 'CC_2',
		'hasc_2': 'HASC_2',
		# 'cpu': 'CPU',
		'geom': 'MULTIPOLYGON'
	}		
	do_import(AdminLevelTwo, shape_file_path, mapping)

def do_import(model, shape_file_path, mapping):
	"""
	Save shapefiles into db
	"""
	def pre_save_callback(sender, instance, *args, **kwargs):
		"""
		Pre-save model signal to allow us set the foreign key properly 
		since LayerMapping will not set the FK
		"""
		field = ""
		if hasattr(sender, "admin_zero"):
			fkey = AdminLevelZero.objects.filter(gid_0=instance.gid_0).first()
			field = "admin_zero"
		if hasattr(sender, "admin_one"):
			fkey = AdminLevelOne.objects.filter(gid_1=instance.gid_1).first()
			field = "admin_one"
		
		if field:
			setattr(instance, field, fkey)

	lm = LayerMapping(model, shape_file_path, mapping, transform=False)
	# temporarily connect pre_save method to allow us set the Foreign Key
	pre_save.connect(pre_save_callback, sender=model)
	lm.save()

	# disconnect pre_save callback
	pre_save.disconnect(pre_save_callback, sender=model)

def validate_custom_polygon(vector_coords):
	"""Validate that the passed custom polygon or vector coordinates 
	is a valid Geometry
	Args:
		vector_coords (string): String representation of a geometry. GeoJson

	Returns:
		tuple(vector, error): If valid coordinates, vector has a GeoJSON while error is empty
	"""
	try:
		vector = GEOSGeometry(vector_coords).geojson
		return (vector, None)
	except Exception as e:
		pass

	try:
		# Attempt to load a using Geojson
		geo_json = json.loads(vector_coords)
		if 'geometry' in geo_json: #check if the object has a 'geometry' key
			vector = GEOSGeometry(str(geo_json['geometry'])).geojson
			return (vector, None)
	except:
		return (None, _("Vector %s is invalid" % (vector_coords)))

def get_vector_from_db(level_id, admin_shapefile_id):
	"""Retrieve the shapefile stored in the database

	Args:
		level_id (int): Administration Level
		admin_shapefile_id (int): ID of the administrative unit shapefile

	Returns:
		tuple(vector, error): If valid model, vector has a GeoJSON while error is empty
	"""
	vector_model = None
	if level_id == -1:
		vector_model = RegionalAdminLevel.objects.filter(id=admin_shapefile_id).first()	
	if level_id == 0:
		vector_model = AdminLevelZero.objects.filter(id=admin_shapefile_id).first()			
	if level_id == 1:
		vector_model = AdminLevelOne.objects.filter(id=admin_shapefile_id).first()
	if level_id == 2:
		vector_model = AdminLevelTwo.objects.filter(id=admin_shapefile_id).first()

	if not vector_model:		
		return (None, _("The selected vector %s does not exist" % (admin_shapefile_id)))		
	return (vector_model.geom.geojson, None)

def get_admin_level_ids_from_db(level_id, admin_shapefile_id):
	"""Retrieve the shapefile stored in the database

	Args:
		level_id (int): Administration Level
		admin_shapefile_id (int): ID of the administrative unit shapefile

	Returns:
		tuple(level0_id, level1_id, level2_id): Tuple of level0, level1 and level2 ids
	"""
	level0_id, level1_id, level2_id = None, None, None
	vector_model = None
	# if level_id == -1:
	# 	vector_model = RegionalAdminLevel.objects.filter(id=admin_shapefile_id).first()	
	if level_id == 0:
		# vector_model = AdminLevelZero.objects.filter(id=admin_shapefile_id).first()			
		level0_id = admin_shapefile_id		
	if level_id == 1:		
		vector_model = AdminLevelOne.objects.filter(id=admin_shapefile_id).first()
		level0_id = vector_model.admin_zero_id
		level1_id = admin_shapefile_id
	if level_id == 2:
		vector_model = AdminLevelTwo.objects.filter(id=admin_shapefile_id).first()
		level0_id = vector_model.admin_one.admin_zero_id
		level1_id = vector_model.admin_one_id
		level2_id = admin_shapefile_id
		
	return (level0_id, level1_id, level2_id)

def validate_coords_within_admin_level(level_id, admin_shapefile_id, vector_coords):
	"""Validates that a custom polygon is within an admin level

	Args:
		level_id (int): Administration Level
		admin_shapefile_id (int): ID of the administrative unit shapefile
		vector_coords (string): String representation of a geometry. GeoJson
	"""
	vector, error = get_vector_from_db(level_id, admin_shapefile_id)
	if error:
		return (False, error)
	return is_subpolygon_contained_inside_polygon(vector_coords, vector)

def is_subpolygon_contained_inside_polygon(child_coords, parent_coords):
	"""Check if a sub-polygon is contained within the boundaries of another polygon

	Args:
		child_coords (geojson): sub-polygon to check if it is within the parent_cords
		parent_coords (geojson): Container polygon
	
	Returns:
		tuple(bool, error): If there is an error, return (False, error) else return (True, None)

	Sample GeoJSON:
		"{\"type\":\"Polygon\",\"coordinates\":[[[8.949565887451172,36.478999869298576],[8.943042755126953,36.449594202722466],[8.94338607788086,36.432055939882105],[8.980979919433594,36.42846494058168],[9.010334014892578,36.434680026625855],[9.007759094238281,36.46657630040234],[8.994541168212889,36.47775760202128],[8.949565887451172,36.478999869298576]]]}"
	"""
	child, error = validate_custom_polygon(child_coords)
	if error:
		return (False, error)
	parent, error = validate_custom_polygon(parent_coords)
	if error:
		return (False, error)

	child = json.loads(child)
	parent = json.loads(parent)

	# Use Shapely to create the polygon
	shape = shapely.geometry.asShape(parent) 

	all_touched = get_settings().raster_clipping_algorithm == "All Touched"
	# Get points of the sub-polygon
	for pnt in child['coordinates'][0]:
		point = shapely.geometry.Point(pnt) # lon, lat

		"""shape.contains used if the point is fully within the polygon. 
		If the point is on the boundary, it returns false. However, if you change 
		contains to intersects you'll get a true result if you want to ensure points on the edge of the polygon are counted."""
		if not all_touched:
			if not shape.contains(point):
				return (False, _("POINT {0} does not fall within the selected polygon".format(pnt)))
		else:
			if not shape.intersects(point):
				return (False, _("POINT {0} does not fall within the selected polygon".format(pnt)))

	return (True, None)
		
def get_vector(admin_level, shapefile_id, custom_vector_coords, admin_0, request, validate_threshold=True):
	"""
	Get vector to use for analysis

	Args:
	 	admin_level (int):
		 	Administrative level of the subject vector (-1, 0, 1, 2)
		shapefile_id (int):
			Id of the shapefile to be used to clip a raster
		custom_vector_coords (geojson):
			Custom drawn polygon
		admin_0 (int):
			Id of country level admin boundary within which to ensure a custom polygon fits.

	Returns:
		tuple (vector, error)
	"""
	# Validate that the vector exists first
	if not custom_vector_coords:
		vector, error = get_vector_from_db(admin_level, shapefile_id)
	else:
		# validate that it is a valid geojson
		vector, error = validate_custom_polygon(custom_vector_coords)
		if not error: # if no error, go ahead and do further validation
			if admin_0:
				"""
				If admin_0 is passed, validate custom polygon falls within the admin_0 
				"""
				res, error = validate_coords_within_admin_level(0, admin_0, custom_vector_coords)
				if error:
					return (None, error)
	# if validate_threshold:
	# 	res, msg = check_queue_threshold(request, vector)
	# 	if not res:
	# 		return (None, msg)
	return (vector, error)

def queue_threshold_exceeded(request, vector):
	"""
	Queued tasks store the request.user as a dict and with the is_authenticated set as True, while
	normal requests have the request.user as an object.

	Returns:
		tuple(Bool, Bool, Str): 
			First element: is True if area of vector is above set threshold
			Second element: is True if request is to be queued
			Third element: Message to be displayed to user
	"""
	# print (request.is_queued)
	# if 'is_queued' in request: # this is a request from a queued task
	# 	return (True, "") 

	def validate(setting, vector, guest_threshold, authenticated_threshold):
		area = calculate_polygon_area(vector)
		if not authenticated:
			if setting.enable_guest_user_limit and area > guest_threshold:
				return (True, False, _("The selected region is too big for processing. You need to sign up first."))
		elif authenticated:
			if setting.enable_signedup_user_limit and area > authenticated_threshold:
				return (True, True, _("""The selected region is too big for processing. The request has been queued. 
									You will be notified when the processing is completed"""))
		return (False, False, "") # any other scenario, just process, no queueing	

	authenticated = request.user['is_authenticated'] if isinstance(request.user, dict) else request.user.is_authenticated
	
	# if there are datasource-specific settings, use those, else use system-wide settings
	compute_threshold = ComputationThreshold.objects.filter(datasource=request.data.get('raster_source')).first()
	if compute_threshold:
		if not compute_threshold.enable_guest_user_limit and not compute_threshold.enable_signedup_user_limit:
			return (False, False, "") # if no limits set, just process, no queueing
		return validate(setting=compute_threshold, vector=vector, 
						guest_threshold=compute_threshold.guest_user_threshold, 
						authenticated_threshold=compute_threshold.authenticated_user_threshold)
	else:
		# if no ComputationThreshold, use system wide settings		
		setts = get_settings()
		if not setts.enable_guest_user_limit and not setts.enable_signedup_user_limit:
			return (False, False, "") # if no limits set, just process, no queueing

		if setts.enable_guest_user_limit or setts.enable_signedup_user_limit:
			return validate(setting=setts, vector=vector, 
					guest_threshold=setts.guest_user_polygon_size_limit,
					authenticated_threshold=setts.signedup_user_polygon_size_limit)
			
	return (False, False, "") # any other scenario, just process, no queueing	

def calculate_polygon_area(geom):
	"""Calculate the area of polygon in square meters 

	Args:
		geom (geojson): GeoJson.

	Returns:
		Area in hectares. To convert to square kilometers, divide by 1000000
	"""
	# geom = "{\"type\":\"Polygon\",\"coordinates\":[[[8.949565887451172,36.478999869298576],[8.943042755126953,36.449594202722466],[8.94338607788086,36.432055939882105],[8.980979919433594,36.42846494058168],[9.010334014892578,36.434680026625855],[9.007759094238281,36.46657630040234],[8.994541168212889,36.47775760202128],[8.949565887451172,36.478999869298576]]]}"
	# geom = {'type': 'Polygon',
	# 	'coordinates': [[[-122., 37.], [-125., 37.],
	# 						[-125., 38.], [-122., 38.],
	# 						[-122., 37.]]]}
	# s = shape(geom)
	s = shapely.geometry.asShape(json.loads(geom))
	proj = partial(pyproj.transform, pyproj.Proj(init='epsg:4326'),
				pyproj.Proj(init='epsg:3857'))

	s_new = transform(proj, s)

	projected_area = transform(proj, s).area

	hectares = projected_area / 10000 #metre squared to hectares
	return hectares

def test_contain():
	custom_coords = "{\"type\":\"Polygon\",\"coordinates\":[[[8.949565887451172,36.478999869298576],[8.943042755126953,36.449594202722466],[8.94338607788086,36.432055939882105],[8.980979919433594,36.42846494058168],[9.010334014892578,36.434680026625855],[9.007759094238281,36.46657630040234],[8.994541168212889,36.47775760202128],[8.949565887451172,36.478999869298576]]]}"
	# custom_coords = "{\"type\":\"Polygon\",\"coordinates\":[[[-1.6259765625,30.14512718337613],[0.263671875,28.188243641850313],[1.7578125,31.728167146023935],[-1.6259765625, 30.14512718337613]]]}"
	return validate_coords_within_admin_level(0, 1, custom_coords)