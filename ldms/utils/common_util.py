from ldms.enums import (AridityIndexEnum, CVIEnum, ClimateQualityIndexEnum, ESAIEnum, 
FireRiskEnum, ForestChangeEnum, ILSWEEnum, LandDegradationChangeEnum, LulcChangeEnum, 
ManagementQualityIndexEnum, PerformanceChangeBinaryEnum, ProductivityCalcEnum, 
ProductivityChangeBinaryEnum, ProductivityChangeTernaryEnum, RUSLEEnum, SOCChangeEnum, 
SoilQualityIndexEnum, TrajectoryChangeBinaryEnum, TrajectoryChangeQuinaryEnum, 
TrajectoryChangeTernaryEnum, VegetationQualityEnum,  ForestChangeQuinaryEnum, ForestChangeTernaryEnum
)
import random
import numpy as np
import string
from rest_framework.response import Response
from django.utils.translation import gettext as _
import django.core.serializers
from django.conf import settings
from ldms.utils.settings_util import get_settings
from django.db.models.base import ModelBase
import datetime
from ldms.models import PublishedComputation
from ldms.enums import ComputationEnum

def get_random_string(length, case=2):
	"""Generate a random string

	Args:
		length (int): Determines the length of the string to be returned 
		case (int, optional): Determines the case of the strings. Defaults to 2.  0 = lowercase,
			1 = uppercase, 2 = mixture of lowercase and uppercase

	Returns:
		string: The generated random string
	"""
	letters = string.ascii_letters
	if case == 0:
		letters = string.ascii_lowercase
	elif case == 1:
		letters = string.ascii_uppercase
	
	result_str = ''.join(random.choice(letters) for i in range(length))
	return result_str

def get_random_int(upper_bound=101):
	"""Generate a random integer

	Returns:
		string: The generated random int

	Parameters:
		upper_bound(int): The upper limit of the range non-inclusive
	"""
	return random.randint(1, 101)

def get_random_floats(min, max, size):
	"""[summary]

	Args:
		min (number): lowerbound
		max (number): upperbound
		size (int): Count of numbers to be returned
	"""
	return np.random.uniform(min, max, size)

def cint(s):
	"""Convert to integer"""
	try: num = int(float(s))
	except: num = 0
	return num

def flt(s):
	"""Convert to float"""
	try: num = float(s)
	except: num = 0.0
	return num


def return_with_error(request, error):	
	if request:
		return Response({"error": error})
	else:
		raise Exception("Error %s " % (error))

def validate_years(start_year, end_year, both_valid=True):
	"""
	Validate the start and end periods

	Args:
		start_year (int): Start year
		end_year (int): End year
		both_valid (bool): If True, both years will be validated
	Returns:
		tuple (start_year, end_year, error)
	"""		

	# Validate that at least one period is specified
	if not start_year and not end_year:
		return (None, None, _("Select at least one period to analyse")) 

	# convert the years into integers
	start_year = cint(start_year) if start_year else None
	end_year = cint(end_year) if end_year else None

	# check start must be earlier than end
	if start_year and end_year:
		if start_year > end_year:
			return (None, None, _("Start period must be earlier than the end period"))

	if both_valid:
		if start_year and end_year:
			if start_year > end_year:
				return (None, None, _("Start period must be earlier than the end period"))
		else:
			return (None, None, _("Start period and end period must both be specified"))
	else:
		# If either is null, assign to the value of the other non-null
		start_year = start_year if start_year else end_year
		end_year = end_year if end_year else start_year

	# if start_year and end_year:
	# 	if start_year > end_year:
	# 		return (None, None, _("Start period must be earlier than the end period"))
	# elif self.analysis_type == LulcCalcEnum.LULC_CHANGE: #both years must be speficied
	# 	return (None, None, _("Both Start period and End period must be specified"))
	# elif self.analysis_type == LulcCalcEnum.LULC: #one year is sufficient
	# 	# If either is null, assign to the value of the other non-null
	# 	start_year = start_year if start_year else end_year
	# 	end_year = end_year if end_year else start_year
	return (start_year, end_year, None)

def validate_dates(start_date, end_date, both_valid=True):
	"""
	Validate the start and end dates

	Args:
		start_date (string or date): Start year
		end_date (string or date): End year
		both_valid (bool): If True, both dates will be validated
	Returns:
		tuple (start_date, end_date, error)
	"""		

	# Validate that at least one period is specified
	if not start_date and not end_date:
		return (None, None, _("Select at least one period to analyse")) 

	# convert the years into integers
	start_date = parse_date(start_date) if start_date else None
	end_date = parse_date(end_date) if end_date else None

	# check start must be earlier than end
	if start_date and end_date:
		if start_date > end_date:
			return (None, None, _("Start date must be earlier than the end date"))

	if both_valid:
		if start_date and end_date:
			if start_date > end_date:
				return (None, None, _("Start date must be earlier than the end date"))
		else:
			return (None, None, _("Start date and end date must both be specified"))
	else:
		# If either is null, assign to the value of the other non-null
		start_date = start_date if start_date else end_date
		end_date = end_date if end_date else start_date

	# if start_date and end_date:
	# 	if start_date > end_date:
	# 		return (None, None, _("Start period must be earlier than the end period"))
	# elif self.analysis_type == LulcCalcEnum.LULC_CHANGE: #both years must be speficied
	# 	return (None, None, _("Both Start period and End period must be specified"))
	# elif self.analysis_type == LulcCalcEnum.LULC: #one year is sufficient
	# 	# If either is null, assign to the value of the other non-null
	# 	start_date = start_date if start_date else end_date
	# 	end_date = end_date if end_date else start_date
	return (start_date, end_date, None)

def format_date(dt, fmt="%Y-%m-%d"):
	return datetime.datetime.strftime(dt, fmt)

def parse_date(dt, fmt="%Y-%m-%d"):
	if not dt:
		return None
	if isinstance(dt, datetime.datetime):
		return dt
	return datetime.datetime.strptime(dt, fmt) 

def as_dict(model):
	"""Convert object to json dict"""
	return django.core.serializers.serialize('json',[model])

def can_queue(request):
	"""return True if the Task can be scheduled"""
	setts = get_settings()
	if not setts.enable_task_scheduling or not request.user.is_authenticated:
		return False
	elif setts.enable_task_scheduling:
		return True
	return False

def list_to_queryset(model, data):
	"""Generate a query set from a list

	Args:
		model ([type]): [description]
		data ([type]): [description]

	Raises:
		ValueError: [description]
		ValueError: [description]

	Returns:
		[type]: [description]
	"""
	if not isinstance(model, ModelBase):
		raise ValueError(
			"%s must be Model" % model
		)
	if not isinstance(data, list):
		raise ValueError(
			"%s must be List Object" % data
		)

	pk_list = [obj.pk for obj in data]
	return model.objects.filter(pk__in=pk_list)

def get_published_computation_by_change_enum(change_enum):
	"""Get associated Published computation by enum type

	Args:
		change_enum (_type_): _description_
	"""
	def _is_instance(enum_type):
		for member in change_enum:
			return isinstance(member, enum_type)
		return False

	xx = _is_instance(LulcChangeEnum)
	if _is_instance(LulcChangeEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.LULC.value).first()

	if _is_instance(ForestChangeEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.FOREST_CHANGE.value).first()

	# if _is_instance(ForestChangeEnum):
	# 	return PublishedComputation.objects.filter(computation_type=ComputationEnum.FOREST_FIRE.value).first()

	if _is_instance(FireRiskEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.FOREST_FIRE_RISK.value).first()

	if _is_instance(SOCChangeEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.SOC.value).first()
	
	if _is_instance(ProductivityChangeBinaryEnum) or _is_instance(ProductivityChangeTernaryEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.PRODUCTIVITY_STATE.value).first()
	
	if _is_instance(TrajectoryChangeBinaryEnum) or _is_instance(TrajectoryChangeTernaryEnum) or _is_instance(TrajectoryChangeQuinaryEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.PRODUCTIVITY_TRAJECTORY.value).first()
	
	if _is_instance(PerformanceChangeBinaryEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.PRODUCTIVITY_PERFORMANCE.value).first()
	
	if _is_instance(ProductivityChangeBinaryEnum) or _is_instance(ProductivityChangeTernaryEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.PRODUCTIVITY.value).first()
	
	if _is_instance(LandDegradationChangeEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.LAND_DEGRADATION.value).first()
	
	if _is_instance(AridityIndexEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.ARIDITY_INDEX.value).first()
	
	if _is_instance(ClimateQualityIndexEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.CLIMATE_QUALITY_INDEX.value).first()
	
	if _is_instance(SoilQualityIndexEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.SOIL_QUALITY_INDEX.value).first()
	
	if _is_instance(VegetationQualityEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.VEGETATION_QUALITY_INDEX.value).first()
	
	if _is_instance(ManagementQualityIndexEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.MANAGEMENT_QUALITY_INDEX.value).first()
	
	if _is_instance(ESAIEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.ESAI.value).first()
	
	if _is_instance(ForestChangeTernaryEnum) or _is_instance(ForestChangeQuinaryEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.FOREST_CARBON_EMISSION.value).first()
	
	if _is_instance(ILSWEEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.ILSWE.value).first()
	
	if _is_instance(RUSLEEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.RUSLE.value).first()
	
	if _is_instance(CVIEnum):
		return PublishedComputation.objects.filter(computation_type=ComputationEnum.COASTAL_VULNERABILITY_INDEX.value).first()