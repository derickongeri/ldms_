from django.contrib.auth import authenticate, login
from user.models import UserProfile
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone
import ldms.logger as logger
from ldms.utils.common_util import as_dict, cint
from django.utils.translation import gettext as _
from rest_framework.response import Response
from django.contrib.auth.hashers import make_password, check_password
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

def authenticate_user(username, password):
	"""
		Check that a user exists
	Args:
		username (string): Username
		password (string): Plain text password
	Returns:
		Instance of the logged in user User model, if not logged in, then None is returned
	"""
	user = authenticate(
		username=username,
		password=password
	)
	return user

@api_view(['POST'])
def do_login(request, username, password):
	user = authenticate_user(username, password)
	if user:
		login(request, username, password)
	else:
		# return an error message
		pass

@api_view(['POST'])
def create_user(request):
	"""
	Create a new user in the database
	Args:
		request (HttpRequest): HttpRequest
	"""
	params = request.data
	first_name = params.get('first_name', None)
	last_name = params.get('last_name', None)
	email = params.get('email', None)
	profession = params.get('profession', None)
	institution = params.get('institution', None)
	title = params.get('title', None)
	password = params.get('password', None)
	
	invalid = validate_mandatory_fields(request,
		['first_name', 'last_name', 'email', 'password']
	)
	if invalid:
		error = _("Missing values for ")
		error = "%s: %s" % (error, str(invalid))
		return Response({"error": error})
	# save user

	user = get_user_model()(
		username=email,
		email=email,
		password=make_password(password),
		first_name=first_name,
		last_name=last_name,
		is_staff=False,
		is_active=True,
		date_joined=timezone.now()
	)

	valid, error = validate_user(request, user)
	if not valid:
		return Response({ "error": error })

	user.save()
	
	# save profile
	profile = UserProfile(
		user=user,
		profession=profession,
		title=title,
		institution=institution
	)
	profile.save()

	return Response({ "username": user.username, "is_active": user.is_active })

def validate_user(request, user):
	"""Do all validations before creationg of users"""	
	# check if user exists
	if get_user_model().objects.filter(username=get_user_model().normalize_username(user.username)).exists():
		json_str = str(request.data)
		msg = "Email already exists"
		logger.log("%s: %s" % (msg, json_str))
		return False, _(msg)
		
	return True, None

def validate_mandatory_fields(request, fields):
	"""
	Validate that all mandatory fields are supplied.
	Returns a list of fields that were not supplied
	"""
	invalid = []
	for field in fields:
		val = request.data.get(field, None)
		if not val:
			invalid.append(field) 
	return invalid

@api_view(['POST'])
# @permission_classes([IsAuthenticated, ])
def update_user(request):
	"""
	Update user details. 
	User making the change must be authenticated.
	Username will not be updated but will only be used to get the correct user to be updated.
	The password will also not be updated
	"""
	params = request.data
	username = params.get('username', None)
	first_name = params.get('first_name', None)
	last_name = params.get('last_name', None)
	email = params.get('email', None)
	profession = params.get('profession', None)
	institution = params.get('institution', None)
	title = params.get('title', None)
	# password = params.get('password', None)
	status = params.get('is_active', False)
	
	invalid = validate_mandatory_fields(request,
		['username', 'first_name', 'last_name', 'email', 'password']
	)
	if invalid:
		error = _("Missing values for ")
		error = "%s: %s" % (error, str(invalid))
		return Response({"error": error})

	user = get_user_model().objects.filter(username=get_user_model().normalize_username(username)).first()
	if user:
		# DO NOT UPDATE THE USERNAME field
		# user.username = username 
		user.email = email
		# user.password = make_password(password)
		user.first_name = first_name
		user.last_name = last_name
		user.is_staff = False
		user.is_active = cint(status)
		user.save()
		
		profile = user.userprofile
		profile.profession = profession
		profile.title = title
		profile.institution = institution
		profile.save()

		return Response({"username": username, "is_active": user.is_active})
	return Response({"error": _("User does not exist")})

@api_view(['POST'])
# @permission_classes([IsAuthenticated, ])
def change_password(request):
	"""
	Update password for the current logged in user.
	User making the change must be authenticated
	"""
	params = request.data
	username = params.get('username', None)
	password = params.get('pwd', False)
	old_pwd = params.get('old_pwd', None)
	invalid = validate_mandatory_fields(request,
		['username', 'old_pwd', 'pwd']
	)
	if invalid:
		error = _("Missing values for ")
		error = "%s: %s" % (error, str(invalid))
		return Response({"error": error})

	user = get_user_model().objects.filter(username=get_user_model().normalize_username(username)).first()
	if user:
		# check supplied old password matches with stored password
		if check_password(old_pwd, user.password): 
			user.password = make_password(password)
			user.save()
			return Response({"username": username, "is_active": user.is_active})
		else:
			return Response({"error": _("Passwords mismatch")})
	return Response({"error": _("User does not exist")})


	
