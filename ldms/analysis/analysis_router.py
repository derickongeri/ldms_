
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.response import Response
from ldms.analysis.lulc import LULC
from ldms.analysis.soc import SOC
from ldms.analysis.productivity import Productivity
from ldms.analysis.land_degradation import LandDegradation
from ldms.analysis.forest_change import ForestChange
from ldms.analysis.forest_fire import ForestFireGEE
from ldms.analysis.forest_fire_risk import ForestFireRiskGEE
from ldms.analysis.medalus import Medalus
from ldms.analysis.forest_carbon_emission import ForestCarbonEmission
from ldms.analysis.ilswe import ILSWE
from ldms.analysis.rusle import RUSLE
from ldms.analysis.coastal_erosion import CoastalVulnerabilityIndex
from ldms.enums import ClimaticRegionEnum, ProductivityCalcEnum, MedalusCalcEnum
from ldms.models import ScheduledTask
from rest_framework.permissions import IsAuthenticated
from ldms.enums import (RasterSourceEnum, RasterCategoryEnum, 
		RUSLEComputationTypeEnum, ILSWEComputationTypeEnum, CVIComputationTypeEnum)
import json 
from django.utils import timezone 
from django.contrib.sites.shortcuts import get_current_site

import django_rq
from django.utils.translation import gettext as _
from django_rq import job
from rq import get_current_job

# from ldms.tasks import add_numbers
from ldms.queue import RedisQueue
from ldms.utils.common_util import can_queue, get_random_int, get_random_string
from rq_scheduler import Scheduler
import datetime
# from django.conf import settings

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from ldms.utils import email_helper
from ldms.utils.settings_util import get_settings
from ldms.utils.vector_util import get_vector, queue_threshold_exceeded, get_admin_level_ids_from_db
from ldms.utils.cache_util import set_cache_key, get_cached_results, generate_cache_key
from ldms.utils.file_util import (get_download_url)

import copy

LULC_ANALYSIS = 1
LULC_CHANGE_ANALYSIS = 2

def get_enqueue_message(request):
	return _("Your task is being processed. The response will be sent to {0} when the results are ready".format(str(request.user.email)))

@api_view(['POST'])
def enqueue_lulc(request):
	return _enqueue(func=lulc, request=request)

@api_view(['POST'])
def enqueue_forest_change(request):
	return _enqueue(func=forest_change, request=request)

@api_view(['POST'])
def enqueue_forest_fire(request):
	return _enqueue(func=forest_fire, request=request)

@api_view(['POST'])
def enqueue_forest_fire_risk(request):
	return _enqueue(func=forest_fire_risk, request=request, force_queue=True)

@api_view(['POST'])
def enqueue_soc(request):
	return _enqueue(func=soc, request=request)

@api_view(['POST'])
def enqueue_state(request):
	return _enqueue(func=state, request=request)

@api_view(['POST'])
def enqueue_trajectory(request):
	return _enqueue(func=trajectory, request=request)

@api_view(['POST'])
def enqueue_performance(request):
	return _enqueue(func=performance, request=request)

@api_view(['POST'])
def enqueue_productivity(request):
	return _enqueue(func=productivity, request=request)

@api_view(['POST'])
def enqueue_land_degradation(request):
	return _enqueue(func=land_degradation, request=request, force_queue=False)

@api_view(['POST'])
def enqueue_aridity(request):
	return _enqueue(func=aridity_index, request=request)

@api_view(['POST'])
def enqueue_climate_quality_index(request):
	return _enqueue(func=climate_quality_index, request=request)

@api_view(['POST'])
def enqueue_soil_quality_index(request):
	return _enqueue(func=soil_quality_index, request=request)

@api_view(['POST'])
def enqueue_vegetation_quality_index(request):
	return _enqueue(func=vegetation_quality_index, request=request)

@api_view(['POST'])
def enqueue_management_quality_index(request):
	return _enqueue(func=management_quality_index, request=request)

@api_view(['POST'])
def enqueue_esai(request):
	return _enqueue(func=esai, request=request, force_queue=True) 

@api_view(['POST'])
def enqueue_forest_carbon_emission(request):
	return _enqueue(func=forest_carbon_emission, request=request)

@api_view(['POST'])
def enqueue_ilswe(request):
	return _enqueue(func=ilswe, request=request)

@api_view(['POST'])
def enqueue_rusle(request):
	return _enqueue(func=rusle, request=request)

@api_view(['POST'])
def enqueue_cvi(request):
	return _enqueue(func=coastal_vulnerability_index, request=request)

def _enqueue(func, request, force_queue=False):
	"""Enqueue computation

	Args:
		func (function): Function to be queued
		request (HttpRequest): Web request
		force_queue (bool, optional): Determine if it has to be queued by force. Defaults to False.
	"""

	def clone_request():
		meta_fields, fields = get_request_fields()
		req = {'META': {}}
		for fld in meta_fields:
			req['META'][fld] = request._request.META.get(fld)
		for fld in fields:
			req[fld] = getattr(request._request, fld)
		req['is_queued'] = True # set to True to distinguish between direct and cloned requests. 
		return req	

	def validate_vector_threshold():
		"""
		Validates the vector to check if it qualifies for queueing
		"""
		params = request.data
		admin_level = params.get('admin_level', None)
		vector_id = params.get('vector', None)
		custom_coords = params.get('custom_coords', None)
		
		vector, err = get_vector(admin_level=admin_level, 
						  shapefile_id=vector_id, 
						  custom_vector_coords=custom_coords, 
						  admin_0=None,
						  request=request
				)
		return queue_threshold_exceeded(request, vector)

	def append_admin_level_args():
		"""Append level 0, level 1 and level2 ids given the passed admin_level

		Returns:
			tuple(level0_id, level1_id, level2_id): Tuple of level0, level1 and level2 ids
		"""
		params = request.data
		admin_level = params.get('admin_level', None)
		vector_id = params.get('vector', None)
		level_0, level_1, level_2 =  get_admin_level_ids_from_db(admin_level, vector_id)
		request.data['admin0'] = level_0
		request.data['admin1'] = level_1
		request.data['admin2'] = level_2

	system_settings = get_settings()
	#If caching enabled, try retrieve cached vals. ForestFire is not cached since GEE urls expire after some time
	if system_settings.enable_cache and func != forest_fire: 
		cached = None
		if "cached" in request.data:
			if request.data.get("cached") == 1 or request.data.get("cached") == "true":
				cached = get_cached_results(request)
		else:
			cached = get_cached_results(request)

		if cached: # return cached results
			val = json.loads(cached)
			return Response(val)

	# do_queue = can_queue(request)
	exceeded, do_queue, msg = validate_vector_threshold()
	
	if exceeded and not do_queue: # if threshold hit and user not allowed to queue, return error/msg
		return Response({ "success": 'false', 'message': msg })

	if force_queue:
		if not request.user.is_authenticated:
			return Response({ "success": 'false', 'message': "This request must be queued. You need to be logged in for the request to be queued." })

		if not msg: # If there is no error
			do_queue = True #if force_queue, set exceeded and  to True if there is no error message			

	# Validate that task scheduling is enabled
	if do_queue and not system_settings.enable_task_scheduling:
		return Response({ "success": 'false', 'message': _("The selected region is too large and therefore requires to be scheduled but task scheduling has not been enabled.") })

	if do_queue:
		# set is_authenticated to True since its already queued and no restrictions on queued since only logged in users can queue
		user = {'is_authenticated': True }
		for fld in get_user_fields():
			user[fld] = getattr(request.user, fld)

		orig_data = copy.copy(request.data)
		append_admin_level_args()
		q = RedisQueue()
		q.enqueue_medium(func=func, 
						request=None, 
						data=request.data, 
						user=user, 
						orig_request=clone_request(), 
						orig_data=orig_data,
						can_queue=do_queue)
		return Response({ "success": 'true', 'message': get_enqueue_message(request) })
	else:
		results = func(request)		
		# we are not caching forest_fire since GEE urls expire after some time
		if system_settings.enable_cache and func != forest_fire:		
			# Only save to cache if there is no error and if caching enabled
			if 'error' not in results.data:				
				set_cache_key(key=generate_cache_key(request.data, request.path), 
						value=json.dumps(eval(str(results.data))))
		return results

def get_user_fields():
	return ["email", "first_name", "last_name", "id", "username"]

def get_request_fields():
	meta_fields = ['SERVER_NAME', 'SERVER_PORT', 'REMOTE_ADDR', 'HTTP_HOST']
	fields = ['path', 'path_info', 'scheme', 'user', '_current_scheme_host']
	return meta_fields, fields

def clone_post_request(data, user, orig_request):
	factory = RequestFactory()
	request = factory.post('/')
	request.data = data
	request.user = user

	meta_fields, fields = get_request_fields()
	for fld in meta_fields:
		request.META[fld] = orig_request['META'].get(fld)
	for fld in fields:
		request.fld = orig_request.get(fld)		
	return request

@api_view(['GET'])
def task_result(request, task_id):	
	try:
		tsk = ScheduledTask.objects.get(pk=task_id)
	except ScheduledTask.DoesNotExist:
		return Response({'success': 'false', 'message': 'The results no longer exist. Please schedule another task'})
	
	from django.forms.models import model_to_dict
	return Response(model_to_dict(tsk))

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
def lulc(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Land Use Land Cover
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
						task_name="lulc", orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data

	# params = request.data	
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	admin_0 = params.get('admin_0', None)
	raster_type = params.get('raster_type', None)
	start_year = params.get('start_year', None)
	end_year = params.get('end_year', None)
	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	show_change = params.get('show_change', False)
	raster_source = params.get('raster_source', RasterSourceEnum.LULC.value)

	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	lulc = LULC(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords,
		raster_type = raster_type,
		start_year=start_year,
		end_year=end_year,
		transform=transform,
		raster_source=raster_source,
		enforce_single_year=True,
		request=request,
	)
	error = ""
	if show_change == False:
		res = lulc.calculate_lulc()
		error = lulc.error
	elif show_change == True:
		res = lulc.calculate_lulc_change()
		error = lulc.error
	
	if can_queue:
		post_analysis_save_task(request, task, res, error, data)
	
	if error:
		return Response({ "error": error })
	else:
		return Response(res)
		
# @api_view(['POST'])
def forest_change(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Forest Change Cover
	We return the values where the land cover is Forest
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
							task_name="forest_change", orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data
	
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	raster_type = params.get('raster_type', None)
	start_year = params.get('start_year', None)
	end_year = params.get('end_year', None)
	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	show_change = params.get('show_change', False)
	raster_source = params.get('raster_source', RasterSourceEnum.LULC.value)
	admin_0 = params.get('admin_0', None)
	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	forest_chg = ForestChange(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords,
		raster_type = raster_type,
		start_year=start_year,
		end_year=end_year,
		transform=transform,
		raster_source=raster_source,
		enforce_single_year=False,
		request=request,
	)
	res = forest_chg.calculate_forest_change()
	error = forest_chg.error	

	if can_queue:
		post_analysis_save_task(request, task, res, error, data)

	if error:
		return Response({ "error": error })
	else:
		return Response(res)

# @api_view(['POST'])
def forest_fire(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Forest Fire  
	Args:
		request (Request): A Web request object

	Returns:
		Response: A Url string where the results can be downloaded as zip
	"""
	can_queue = False # Do not queue ForestFire since it is being processed by GEE
	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
						task_name="forest_fire", orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data
	
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	raster_type = params.get('raster_type', None)

	prefire_start = params.get('prefire_start', None)
	prefire_end = params.get('prefire_end', None)

	postfire_start = params.get('postfire_start', None)
	postfire_end = params.get('postfire_end', None)

	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	raster_source = params.get('raster_source', RasterSourceEnum.LANDSAT8.value)
	admin_0 = params.get('admin_0', None)

	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	frst_fire = ForestFireGEE(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords,
		prefire_start = prefire_start,
		prefire_end=prefire_end,
		postfire_start=postfire_start,
		postfire_end=postfire_end,
		transform=transform,
		raster_source=raster_source,
		request=request,
	)
	res = frst_fire.calculate_forest_fire()
	error = frst_fire.error	

	if can_queue:
		post_analysis_save_task(request, task, res, error, data)

	if error:
		return Response({ "error": error })
	else:
		return Response(res)

def forest_fire_risk(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Forest Fire Risk
	Args:
		request (Request): A Web request object

	Returns:
		Response: A Url string where the results can be downloaded as zip
	"""
	# can_queue = False # Do not queue ForestFire since it is being processed by GEE
	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
						task_name="forest_fire_risk", orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data
	
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)	

	start = params.get('start_date', None)
	end = params.get('end_date', None)

	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	# raster_source = params.get('raster_source', RasterSourceEnum.LANDSAT8.value)
	admin_0 = params.get('admin_0', None)

	# raster_source = map_raster_source(raster_source)
	# if raster_source == None:
	# 	return Response({ "error": _("Invalid value for raster source") })

	frst_fire = ForestFireRiskGEE(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords,
		start_date = start,
		end_date=end,
		transform=transform,
		request=request,
	)
	res = frst_fire.calculate_fire_risk()
	error = frst_fire.error	

	if can_queue:
		post_analysis_save_task(request, task, res, error, data)

	if error:
		return Response({ "error": error })
	else:
		return Response(res)

def map_raster_source(raster_source_val):
	"""
	Get RasterSourceEnum given a value
	"""
	try:
		return RasterSourceEnum(raster_source_val)
	except ValueError:
		return None

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
def soc(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Soil Organic Carbon 
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
						task_name="soc", orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data
	
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	raster_type = params.get('raster_type', None)
	start_year = params.get('start_year', None)
	end_year = params.get('end_year', None)
	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	show_change = params.get('show_change', False)
	reference_raster = params.get('reference_raster', 3)
	raster_source = params.get('raster_source', RasterSourceEnum.LULC.value)
	admin_0 = params.get('admin_0', None)

	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	soc = SOC(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords, # custom_coords,
		raster_type = raster_type,
		start_year=start_year,
		end_year=end_year,
		transform=transform,
		write_to_disk=True,
		climatic_region=ClimaticRegionEnum.TemperateDry,
		reference_soc=reference_raster,
		raster_source=raster_source,
		request=request,
	)

	res = ""
	error = ""
	if show_change == False:
		# res = soc.calculate_soc_change()
		# error = soc.error
		pass
	elif show_change == True:
		res = soc.calculate_soc_change()
		error = soc.error 

	if can_queue:
		post_analysis_save_task(request, task, res, error, data)

	if error:
		return Response({ "error": error })
	else:
		return Response(res)

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
def trajectory(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Compute productivity trajectory sub-indicator

	Args:
		request (Request): A Web request object
	
	Returns:
		Response: A JSON string with statistic values
	"""
	return dispatch_productivity(request, ProductivityCalcEnum.TRAJECTORY, data=data, 
			user=user, orig_request=orig_request, can_queue=can_queue, 
			orig_data=orig_data)
	
# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
def state(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Compute productivity trajectory sub-indicator

	Args:
		request (Request): A Web request object
	
	Returns:
		Response: A JSON string with statistic values
	"""
	return dispatch_productivity(request, ProductivityCalcEnum.STATE, data=data, 
			user=user, orig_request=orig_request, can_queue=can_queue, 
			orig_data=orig_data)
	
# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
def performance(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Compute productivity performance sub-indicator

	Args:
		request (Request): A Web request object
	
	Returns:
		Response: A JSON string with statistic values
	"""
	return dispatch_productivity(request, ProductivityCalcEnum.PERFORMANCE, data=data, 
			user=user, orig_request=orig_request, can_queue=can_queue, 
			orig_data=orig_data)

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
def productivity(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Compute productivity indicator

	Args:
		request (Request): A Web request object
	
	Returns:
		Response: A JSON string with statistic values
	"""
	return dispatch_productivity(request, ProductivityCalcEnum.PRODUCTIVITY, data=data, 
				user=user, orig_request=orig_request, can_queue=can_queue, 
				orig_data=orig_data)

def dispatch_productivity(request, productivity_calc_enum, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Compute productivity sub-indicators

	Args:
		request: Request object
		productivity_calc_enum (ProductivityCalcEnum)
	"""	
	if productivity_calc_enum == ProductivityCalcEnum.TRAJECTORY:
		task_name = "trajectory"
	if productivity_calc_enum == ProductivityCalcEnum.STATE:
		task_name = "state"
	if productivity_calc_enum == ProductivityCalcEnum.PERFORMANCE:
		task_name = "performance"
	if productivity_calc_enum == ProductivityCalcEnum.PRODUCTIVITY:
		task_name = "productivity"

	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
						task_name=task_name, orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data

	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	raster_type = params.get('raster_type', None)
	start_year = params.get('start_year', None)
	end_year = params.get('end_year', None)
	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	show_change = params.get('show_change', False)
	reference_eco_units = params.get('reference_eco_units', None)
	raster_source = params.get('raster_source', RasterSourceEnum.MODIS.value)
	admin_0 = params.get('admin_0', None)
	veg_index = params.get('veg_index', RasterCategoryEnum.NDVI.value)
	version = params.get("version", 1)
	class_map = params.get('class_map', 3)

	# reference_raster = params.get('reference_raster', 3)
	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	prod = Productivity(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords, # custom_coords,
		raster_type = raster_type,
		start_year=start_year,
		end_year=end_year,
		transform=transform,
		write_to_disk=True,
		climatic_region=ClimaticRegionEnum.TemperateDry,
		# reference_soc=reference_raster,
		show_change=show_change,
		request=request,
		raster_source=raster_source,
		reference_eco_units=reference_eco_units,
		veg_index=veg_index,
		version=version,
		class_map=class_map
	)
	if productivity_calc_enum == ProductivityCalcEnum.TRAJECTORY:
		res = prod.calculate_trajectory()
	if productivity_calc_enum == ProductivityCalcEnum.STATE:
		res = prod.calculate_state()
	if productivity_calc_enum == ProductivityCalcEnum.PERFORMANCE:
		res = prod.calculate_performance()
	if productivity_calc_enum == ProductivityCalcEnum.PRODUCTIVITY:
		res = prod.calculate_productivity()

	error = prod.error 

	if can_queue:
		post_analysis_save_task(request, task, res, error, data)

	if error:
		return Response({ "error": error })
	else:
		return Response(res)

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
def land_degradation(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Land Degradation
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
							task_name="land_degradation", orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data
	
	params = request.data
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	raster_type = params.get('raster_type', None)
	start_year = params.get('start_year', None)
	end_year = params.get('end_year', None)
	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	show_change = params.get('show_change', False)
	reference_eco_units = params.get('reference_eco_units', None)
	reference_soc = params.get('reference_raster', None)
	raster_source = params.get('raster_source', RasterSourceEnum.MODIS.value)
	admin_0 = params.get('admin_0', None)
	veg_index = params.get('veg_index', RasterCategoryEnum.NDVI.value)

	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	prod = LandDegradation(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords, # custom_coords,
		raster_type = raster_type,
		start_year=start_year,
		end_year=end_year,
		transform=transform,
		write_to_disk=True,
		climatic_region=ClimaticRegionEnum.TemperateDry,
		# reference_soc=reference_raster,
		show_change=show_change,
		request=request,
		reference_soc=reference_soc,
		raster_source=raster_source,
		reference_eco_units=reference_eco_units,
		veg_index=veg_index
	)

	res = prod.calculate_land_degradation()
	error = prod.error 

	if can_queue:
		post_analysis_save_task(request, task, res, error, data)

	if error:
		return Response({ "error": error })
	else:
		return Response(res)

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
def aridity_index(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Aridity Indx
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	return dispatch_medalus(request, MedalusCalcEnum.ARIDITY_INDEX, data=data, 
					user=user, orig_request=orig_request, can_queue=can_queue, 
					orig_data=orig_data)

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
def climate_quality_index(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Climate Quality Index
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	return dispatch_medalus(request, MedalusCalcEnum.CLIMATE_QUALITY_INDEX, data=data, 
					user=user, orig_request=orig_request, can_queue=can_queue, 
					orig_data=orig_data)

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
def soil_quality_index(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Soil Quality Index
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	return dispatch_medalus(request, MedalusCalcEnum.SOIL_QUALITY_INDEX, data=data, 
					user=user, orig_request=orig_request, can_queue=can_queue, 
					orig_data=orig_data)

def vegetation_quality_index(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Vegetation Quality Index
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	return dispatch_medalus(request, MedalusCalcEnum.VEGETATION_QUALITY_INDEX, data=data, 
					user=user, orig_request=orig_request, can_queue=can_queue, 
					orig_data=orig_data)

def management_quality_index(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Management Quality Index
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	return dispatch_medalus(request, MedalusCalcEnum.MANAGEMENT_QUALITY_INDEX, data=data, 
					user=user, orig_request=orig_request, can_queue=can_queue, 
					orig_data=orig_data)

def esai(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate ESAI
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	return dispatch_medalus(request, MedalusCalcEnum.ESAI, data=data, 
					user=user, orig_request=orig_request, can_queue=can_queue, 
					orig_data=orig_data)

def dispatch_medalus(request, medalus_calc_enum, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Compute Medalus indicies

	Args:
		request: Request object
		medalus_calc_enum (MedalusCalcEnum)
	"""	
	if medalus_calc_enum == MedalusCalcEnum.ARIDITY_INDEX:
		task_name = "aridity_index"
	if medalus_calc_enum == MedalusCalcEnum.CLIMATE_QUALITY_INDEX:
		task_name = "climate_quality_index"
	if medalus_calc_enum == MedalusCalcEnum.SOIL_QUALITY_INDEX:
		task_name = "soil_quality_index"
	if medalus_calc_enum == MedalusCalcEnum.VEGETATION_QUALITY_INDEX:
		task_name = "vegetation_quality_index"
	if medalus_calc_enum == MedalusCalcEnum.MANAGEMENT_QUALITY_INDEX:
		task_name = "management_quality_index"
	if medalus_calc_enum == MedalusCalcEnum.ESAI:
		task_name = "esai"

	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
						task_name=task_name, orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data

	params = request.data
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	raster_type = params.get('raster_type', None)
	start_year = params.get('start_year', None)
	end_year = params.get('end_year', None)
	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	show_change = params.get('show_change', False)
	reference_eco_units = params.get('reference_eco_units', None)
	reference_soc = params.get('reference_raster', None)
	raster_source = params.get('raster_source', RasterSourceEnum.MODIS.value)
	admin_0 = params.get('admin_0', None)
	
	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	medalus = Medalus(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords, # custom_coords,
		raster_type = raster_type,
		start_year=start_year,
		end_year=end_year,
		transform=transform,
		write_to_disk=True,
		# climatic_region=ClimaticRegionEnum.TemperateDry,
		# reference_soc=reference_raster,
		show_change=show_change,
		request=request,
		# reference_soc=reference_soc,
		raster_source=raster_source,
		reference_eco_units=reference_eco_units,
		# veg_index=veg_index
	)

	if medalus_calc_enum == MedalusCalcEnum.ARIDITY_INDEX:
		res = medalus.calculate_aridity_index()
	if medalus_calc_enum == MedalusCalcEnum.CLIMATE_QUALITY_INDEX:
		res = medalus.calculate_climate_quality_index()
	if medalus_calc_enum == MedalusCalcEnum.SOIL_QUALITY_INDEX:
		res = medalus.calculate_soil_quality_index()
	if medalus_calc_enum == MedalusCalcEnum.VEGETATION_QUALITY_INDEX:
		res = medalus.calculate_vegetation_quality_index()
	if medalus_calc_enum == MedalusCalcEnum.MANAGEMENT_QUALITY_INDEX:
		res = medalus.calculate_management_quality_index()
	if medalus_calc_enum == MedalusCalcEnum.ESAI:
		res = medalus.calculate_esai()

	error = medalus.error

	if can_queue:
		post_analysis_save_task(request, task, res, error, data)
	# else: # try cache results if no error
	# 	if not error:
	# 		cache_results(params, res, error)

	if error:
		return Response({ "error": error })
	else:
		return Response(res)

def forest_carbon_emission(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Forest Carbon Emission
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
						task_name="lulc", orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data

	# params = request.data	
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	admin_0 = params.get('admin_0', None)
	raster_type = params.get('raster_type', None)
	start_year = params.get('start_year', None)
	end_year = params.get('end_year', None)
	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	show_change = params.get('show_change', False)
	raster_source = params.get('raster_source', RasterSourceEnum.HANSEN.value)
	muf = params.get('muf', None)
	mfu_forest_threshold = params.get('mfu_forest_threshold', None)
	carbon_stock = params.get('carbon_stock', None)
	degradation_emission_proportion = params.get('degradation_emission_proportion', None)

	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	carbon_emission = ForestCarbonEmission(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords,
		raster_type = raster_type,
		start_year=start_year,
		end_year=end_year,
		transform=transform,
		raster_source=raster_source,
		enforce_single_year=True,
		muf=muf,
		mfu_forest_threshold=mfu_forest_threshold,
		carbon_stock=carbon_stock,
		degradation_emission_proportion=degradation_emission_proportion,
		request=request,
	)
	error = ""
	# if show_change == False:
	res = carbon_emission.calculate_carbon_emission()
	error = carbon_emission.error
	# elif show_change == True:
	# 	res = carbon_emission.calculate_lulc_change()
	# 	error = carbon_emission.error
	
	if can_queue:
		post_analysis_save_task(request, task, res, error, data)
	
	if error:
		return Response({ "error": error })
	else:
		return Response(res)

def ilswe(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Land Degradation
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	def get_computation_type():
		comp_type = params.get('computation_type', None)
		comp_type = comp_type.title() if comp_type else None
		if comp_type == ILSWEComputationTypeEnum.VEGETATION_COVER.label.title():
			return ILSWEComputationTypeEnum.VEGETATION_COVER
		if comp_type == ILSWEComputationTypeEnum.SOIL_CRUST.label.title():
			return ILSWEComputationTypeEnum.SOIL_CRUST
		if comp_type == ILSWEComputationTypeEnum.SOIL_ROUGHNESS.label.title():
			return ILSWEComputationTypeEnum.SOIL_ROUGHNESS
		if comp_type == ILSWEComputationTypeEnum.ERODIBLE_FRACTION.label.title():
			return ILSWEComputationTypeEnum.ERODIBLE_FRACTION
		if comp_type == ILSWEComputationTypeEnum.CLIMATE_EROSIVITY.label.title():
			return ILSWEComputationTypeEnum.CLIMATE_EROSIVITY
		if comp_type == ILSWEComputationTypeEnum.ILSWE.label.title():
			return ILSWEComputationTypeEnum.ILSWE
		return ILSWEComputationTypeEnum.ILSWE

	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
							task_name="ilswe", orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data
	
	params = request.data
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	raster_type = params.get('raster_type', None)
	start_year = params.get('start_year', None)
	end_year = params.get('end_year', None)
	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	show_change = params.get('show_change', False)
	reference_eco_units = params.get('reference_eco_units', None)
	reference_soc = params.get('reference_raster', None)
	raster_source = params.get('raster_source', RasterSourceEnum.MODIS.value)
	admin_0 = params.get('admin_0', None)
	veg_index = params.get('veg_index', RasterCategoryEnum.NDVI.value)
	computation_type = get_computation_type()

	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	ilswe = ILSWE(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords, # custom_coords,
		raster_type = raster_type,
		start_year=start_year,
		end_year=end_year,
		transform=transform,
		write_to_disk=True,
		climatic_region=ClimaticRegionEnum.TemperateDry,
		# reference_soc=reference_raster,
		show_change=show_change,
		request=request,
		reference_soc=reference_soc,
		raster_source=raster_source,
		reference_eco_units=reference_eco_units,
		veg_index=veg_index,
		computation_type=computation_type
	)

	res = ilswe.calculate_ilswe()
	error = ilswe.error 

	if can_queue:
		post_analysis_save_task(request, task, res, error, data)

	if error:
		return Response({ "error": error })
	else:
		return Response(res)

def rusle(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Land Degradation
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	def get_computation_type():
		comp_type = params.get('computation_type', None)
		comp_type = comp_type.title() if comp_type else None
		if comp_type == RUSLEComputationTypeEnum.RAINFALL_EROSIVITY.label.title():
			return RUSLEComputationTypeEnum.RAINFALL_EROSIVITY
		if comp_type == RUSLEComputationTypeEnum.SOIL_ERODIBILITY.label.title():
			return RUSLEComputationTypeEnum.SOIL_ERODIBILITY
		if comp_type == RUSLEComputationTypeEnum.SLOPE_STEEPNESS.label.title():
			return RUSLEComputationTypeEnum.SLOPE_STEEPNESS
		if comp_type == RUSLEComputationTypeEnum.COVER_MANAGEMENT.label.title():
			return RUSLEComputationTypeEnum.COVER_MANAGEMENT
		if comp_type == RUSLEComputationTypeEnum.CONSERVATION_PRACTICES.label.title():
			return RUSLEComputationTypeEnum.CONSERVATION_PRACTICES
		if comp_type == RUSLEComputationTypeEnum.RUSLE.label.title():
			return RUSLEComputationTypeEnum.RUSLE

		return RUSLEComputationTypeEnum.RUSLE

	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
							task_name="rusle", orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data
	
	params = request.data
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	raster_type = params.get('raster_type', None)
	start_year = params.get('start_year', None)
	end_year = params.get('end_year', None)
	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	show_change = params.get('show_change', False)
	reference_eco_units = params.get('reference_eco_units', None)
	reference_soc = params.get('reference_raster', None)
	raster_source = params.get('raster_source', RasterSourceEnum.MODIS.value)
	admin_0 = params.get('admin_0', None)
	veg_index = params.get('veg_index', RasterCategoryEnum.NDVI.value)
	computation_type = get_computation_type()

	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	rusle = RUSLE(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords, # custom_coords,
		raster_type = raster_type,
		start_year=start_year,
		end_year=end_year,
		transform=transform,
		write_to_disk=True,
		climatic_region=ClimaticRegionEnum.TemperateDry,
		# reference_soc=reference_raster,
		show_change=show_change,
		request=request,
		reference_soc=reference_soc,
		raster_source=raster_source,
		reference_eco_units=reference_eco_units,
		veg_index=veg_index,
		computation_type=computation_type
	)

	res = rusle.calculate_rusle()
	error = rusle.error 

	if can_queue:
		post_analysis_save_task(request, task, res, error, data)

	if error:
		return Response({ "error": error })
	else:
		return Response(res)

def coastal_vulnerability_index(request, data=None, user=None, orig_request=None, can_queue=False, orig_data=None):
	"""Generate Costal Vulnerability Index
	
	Args:
		request (Request): A Web request object

	Returns:
		Response: A JSON string with statistic values
	"""	
	def get_computation_type():
		comp_type = params.get('computation_type', None)
		comp_type = comp_type.title() if comp_type else None
		if comp_type == CVIComputationTypeEnum.GEOMORPHOLOGY.label.title():
			return CVIComputationTypeEnum.GEOMORPHOLOGY
		if comp_type == CVIComputationTypeEnum.COASTAL_SLOPE.label.title():
			return CVIComputationTypeEnum.COASTAL_SLOPE
		if comp_type == CVIComputationTypeEnum.SEALEVEL_CHANGE.label.title():
			return CVIComputationTypeEnum.SEALEVEL_CHANGE
		if comp_type == CVIComputationTypeEnum.SHORELINE_EROSION.label.title():
			return CVIComputationTypeEnum.SHORELINE_EROSION
		if comp_type == CVIComputationTypeEnum.TIDE_RANGE.label.title():
			return CVIComputationTypeEnum.TIDE_RANGE
		if comp_type == CVIComputationTypeEnum.WAVE_HEIGHT.label.title():
			return CVIComputationTypeEnum.WAVE_HEIGHT
		if comp_type == CVIComputationTypeEnum.CVI.label.title():
			return CVIComputationTypeEnum.CVI 
		return CVIComputationTypeEnum.CVI

	if can_queue:
		job, task = pre_analysis_save_task(request=orig_request, data=data, user=user, 
							task_name="cvi", orig_data=orig_data)
		
	params = data
	if not request:
		request = clone_post_request(data, user, orig_request)
	else:
		params = request.data
	
	params = request.data
	vector_id = params.get('vector', None)
	admin_level = params.get('admin_level', None)
	raster_type = params.get('raster_type', None)
	start_year = params.get('start_year', None)
	end_year = params.get('end_year', None)
	custom_coords = params.get('custom_coords', None)
	transform = params.get('transform', "area")
	show_change = params.get('show_change', False)
	reference_eco_units = params.get('reference_eco_units', None)
	reference_soc = params.get('reference_raster', None)
	raster_source = params.get('raster_source', RasterSourceEnum.MODIS.value)
	admin_0 = params.get('admin_0', None)
	veg_index = params.get('veg_index', RasterCategoryEnum.NDVI.value)
	computation_type = get_computation_type()

	raster_source = map_raster_source(raster_source)
	if raster_source == None:
		return Response({ "error": _("Invalid value for raster source") })

	cvi = CoastalVulnerabilityIndex(
		admin_0=admin_0,
		admin_level=admin_level,
		shapefile_id = vector_id,
		custom_vector_coords = custom_coords, # custom_coords,
		raster_type = raster_type,
		start_year=start_year,
		end_year=end_year,
		transform=transform,
		write_to_disk=True,
		climatic_region=ClimaticRegionEnum.TemperateDry,
		# reference_soc=reference_raster,
		show_change=show_change,
		request=request,
		reference_soc=reference_soc,
		raster_source=raster_source,
		reference_eco_units=reference_eco_units,
		veg_index=veg_index,
		computation_type=computation_type
	)

	res = cvi.calculate_cvi()
	error = cvi.error 

	if can_queue:
		post_analysis_save_task(request, task, res, error, data)

	if error:
		return Response({ "error": error })
	else:
		return Response(res)

def pre_analysis_save_task(request, data, user, task_name, orig_data):
	"""Save task"""
	job = get_current_job()
	print("User email: ",  user['email'] if user else "" )
	task = ScheduledTask.objects.create(
		owner=user['email'] if user else "",
		job_id=job.get_id() if job else get_random_string(length=10),
		name=task_name,
		method=request['path'],
		#args=json.dumps(json.loads(data)) if data else "{}",
		args=json.dumps(data) if data else "{}",		
		orig_args=json.dumps(orig_data) if orig_data else "{}",
		status=_("Processing"),
		request=request,
	)
	return job, task
	
def post_analysis_save_task(request, task, res, error, data):
	"""Update task with results of analysis"""
	def parse_result():
		if isinstance(res, dict):
			return json.dumps(eval(str(res)))
		return res

	def cache_results():
		# cache results. Only save to cache if there is no error
		if not error:
			"""To generate key, use data and not request.data since data contains 
			the original user payload while request.data may have been interfered with 
			when adminlevel one and two ids are appended"""
			set_cache_key(key=generate_cache_key(json.loads(task.orig_args), task.method), 
					value=parse_result())

	task.result = parse_result() if not error else ""
	task.error = error
	task.succeeded = True if not error else False
	task.status = _("Finished") if not error else _("Failed")
	task.completed_on = timezone.now()
	task.save()

	if get_settings().enable_cache:
		cache_results()
		# cache_results(task.orig_args, res, error)
	notify_user(request, task, task.owner)	

def notify_user(request, task, email_addr):
	"""Send an email"""
	current_site = get_current_site(request)
	user = get_user_model().objects.filter(email=email_addr).first()
	setts = get_settings()
	message = render_to_string('ldms/task_complete.html', {
			'user': user,
			'domain': current_site.domain,
			'endpoint': setts.task_results_url.rstrip("/") + "/" + str(task.id),
			'task': task,
		})
	to_email = user.email
	subject = _("Task Completed")

	task.notified_owner = True
	task.notified_on = timezone.now()
	task.save()
	return email_helper.send_email(subject, message, [to_email])

@api_view(["GET"])
def forest_fire_qml(request):
	"""
	Get the url of the forest fire qml
	"""
	url = get_download_url(request, "Fire_Severity.qml", use_static_dir=False)
	return Response({ "success": 'true', 'url': url })

# @api_view(['POST'])
def test_queue():
	# Schedule the job with the form parameters
	url = "http://gitlab.com"
	# scheduler = Scheduler(name, interval=interval,
	#                      connection=get_connection(name))
	scheduler = django_rq.get_scheduler('default')
	job = scheduler.schedule(
		scheduled_time=datetime.datetime.now(),
		func=scheduled_get_url_words,
		args=[url],
		interval=10,
		repeat=5,
	)
	# scheduler.schedule(
	# 	scheduled_time=datetime.utcnow(), # Time for first execution, in UTC timezone
	# 	func=func,                     # Function to be queued
	# 	args=[arg1, arg2],             # Arguments passed into function when executed
	# 	kwargs={'foo': 'bar'},         # Keyword arguments passed into function when executed
	# 	interval=60,                   # Time before the function is called again, in seconds
	# 	repeat=10,                     # Repeat this number of times (None means repeat forever)
	# 	meta={'foo': 'bar'}            # Arbitrary pickleable data on the job itself
	# )
	return Response({ "error": _("Invalid value for raster source") })


@api_view(["GET"])
def test_render(request):
	message = render_to_string('ldms/task_complete.html', {
		'user': {"email": "stev"},
		'domain': "current_site.domain",
		'task': {"id": 3},
	})
	email_helper.send_email("subject", message, ["stevenyaga@gmail.com"])
	return Response({"message": message})

@job
def add_numbers(a, b):
	return a + b

@job
def scheduled_get_url_words(url):
	"""
	This creates a ScheduledTask instance for each group of
	scheduled task - each time this scheduled task is run
	a new instance of ScheduledTaskInstance will be created
	"""
	print ("Starting job execution")
	job = get_current_job()

	task, created = ScheduledTask.objects.get_or_create(
		job_id=job.get_id(),
		name=url
	)
	response = requests.get(url)
	response_len = len(response.text)
	# ScheduledTaskInstance.objects.create(
	#     scheduled_task=task,
	#     result = response_len,
	# )
	print ("Completed job execution")
	return Response({ "error": response_len })
	