from django.shortcuts import render

from rest_framework import status
from rest_framework.generics import CreateAPIView
from rest_framework.generics import RetrieveAPIView
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework import generics
from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from user.backends import JWTAuthentication
#  rest_framework_simplejwt.authentication import JWTTokenUserAuthentication
from user.serializers import (UserRegistrationSerializer, UserLoginSerializer, 
	UserProfileSerializer, UserAccountActivateSerializer,
	RequestResetForgottenPasswordSerializer, ResetForgottenPasswordSerializer)
from user.models import UserProfile, CustomUser
from django.utils.translation import gettext as _
from django.shortcuts import get_object_or_404
from django.contrib.auth.password_validation import validate_password
from user.serializers import ChangePasswordSerializer, UserUpdateSerializer
from user.permissions import IsAdminOrSelf
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.conf import settings
from user.utils import email_util
from ldms.utils.settings_util import get_settings
from ldms.utils import email_helper

class UserRegistrationView(CreateAPIView):
	serializer_class = UserRegistrationSerializer
	permission_classes = (AllowAny, )
	
	def post(self, request):
		"""
		Register a user
		"""
		# restore those native datatypes into a dictionary of validated data.
		serializer = self.serializer_class(data=request.data)

		# checks if the data is as per serializer fields, otherwise throws an exception
		# serializer.is_valid(raise_exception=True)
		if not serializer.is_valid():
			return Response(serializer.errors, status.HTTP_400_BAD_REQUEST) 

		# return an object instance, based on the validated data.
		serializer.validated_data.is_active = False
		serializer.save()

		message = _('User registered successfully')
		if get_settings().enable_user_account_email_activation: # settings.ENABLE_EMAIL_ACTIVATION:
			self.send_activate_email(request, serializer.validated_data['email'])
			message = _("Please confirm your email address to complete the registration")
		
		status_code = status.HTTP_201_CREATED
		response = {
			'success': 'true',
			'status_code': status_code,
			'message': message
		} 
		return Response(response, status=status_code)

	def send_activate_email(self, request, email_addr):
		"""Send an email"""
		current_site = get_current_site(request)
		user = CustomUser.objects.filter(email=email_addr).first()
		setts = get_settings()
		uid = urlsafe_base64_encode(force_bytes(user.pk))
		token = default_token_generator.make_token(user)

		message = render_to_string('user/activate_account.html', {
				'user': user,
				'domain': current_site.domain,
				'uid': uid,
				'token': token,
				'endpoint': setts.account_activation_url.rstrip("/") + "/" + uid + "/" + token + "/",
			})
		to_email = user.email
		subject = _("Activate your account")
		# return email_util.send(subject, message, to_email)
		return email_helper.send_email(subject, message, [to_email])		
		
class UserAccountActivationView(viewsets.ReadOnlyModelViewSet):
	"""
	View to manage activation of user accounts	
	"""
	# See https://medium.com/@frfahim/django-registration-with-confirmation-email-bb5da011e4ef

	serializer_class = UserAccountActivateSerializer
	# def activate(self):#, uidb64, token):
	def activate(self, request, *args, **kwargs):
		"""Activate user account"""
		try:
			uidb64 = self.kwargs.get('uidb64', None) # self.request.query_params.get('uidb64', None)
			token = self.kwargs.get('token', None) #self.request.query_params.get('token', None)
			uid = urlsafe_base64_decode(uidb64).decode()
			user = CustomUser.objects.get(pk=uid)
		except(TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
			user = None
		
		if user is not None and default_token_generator.check_token(user, token):
			user.is_active = True
			user.save()
			status_code = status.HTTP_200_OK
			response = {
				'success': 'true',
				'status_code': status_code,
				'message': _('Your account has been activated. You can now login to your account'),
			}
		else:
			status_code = status.HTTP_400_BAD_REQUEST
			response = {
				'success': 'false',
				'status_code': status_code,
				'message': _('Activation link is invalid'),
			}
		return Response(response, status=status_code)

class UserLoginView(RetrieveAPIView):

	queryset = CustomUser.objects.all()
	permission_classes = (AllowAny, )
	serializer_class = UserLoginSerializer

	def post(self, request):
		"""
		Login and return a token generated for user if successful
		"""
		serializer = self.serializer_class(data=request.data)
		if not serializer.is_valid():
			return Response(serializer.errors, status.HTTP_400_BAD_REQUEST) 
			
		response = {
			'success': 'true',
			'status_code': status.HTTP_200_OK,
			'message': _('User logged in successfully'),
			'token': serializer.data['token'],
		}
		status_code = status.HTTP_200_OK
		return Response(response, status=status_code)

class UserList(generics.ListAPIView):

	queryset = CustomUser.objects.all()
	serializer_class = UserRegistrationSerializer
	permission_classes = [IsAuthenticated, ]

	def get_queryset(self):
		"""
		If superuser, return all users, else return only the current user
		"""
		if self.request.user.is_superuser or self.request.user.is_admin:
			return CustomUser.objects.all()
		else:
			return CustomUser.objects.filter(email=self.request.user.email)
		
	def list(self, request):
		# Note the use of `get_queryset()` instead of `self.queryset`
		queryset = self.get_queryset()
		serializer = UserRegistrationSerializer(queryset, many=True)
		return Response(serializer.data)

class UserRetrieveView(RetrieveUpdateAPIView):
	"""
	RetrieveAPIView as we want to retrieve a single instance.
	Also, we have set permission_classes to IsAuthenticated so
	the only user who is authenticated can hit this API and the 
	authentication_class should be JWT.
	"""	
	permission_classes = (IsAuthenticated, IsAdminOrSelf)
	authentication_classes = (JWTAuthentication, ) #(JSONWebTokenAuthentication, )
	
	def get_object(self, queryset=None, email=None):
		"""If no email supplied, return the current user"""
		if not email:
			obj = self.request.user
		else:
			obj = CustomUser.objects.filter(email=email).first()
		# Ensure that permission classes (IsAuthenticated, IsAdminOrSelf) are applied
		self.check_object_permissions(self.request, obj)
		return obj

	def get(self, request):
		user = self.get_object(email=request.query_params.get('email', None))
		if user:
			profile = UserProfile.objects.get(user=request.user)
			status_code = status.HTTP_200_OK
			response = {
				'success': 'true',
				'status_code': status_code,
				'message': _('User profile fetched successfully'),
				'data': [{
					'email': user.email,
					'first_name': user.first_name,
					'last_name': user.last_name,
					'profession': profile.profession,
					'institution': profile.institution,
					'title': profile.title,
					'is_active': int(user.is_active),
					'is_admin': int(user.is_admin),
					# 'is_superuser': int(user.is_superuser),
					'can_upload_custom_shapefile': int(profile.can_upload_custom_shapefile),
					'can_upload_standard_raster': int(profile.can_upload_standard_raster)
				}]
			}
		else:
			status_code = status.HTTP_400_BAD_REQUEST
			response = {
				'success': 'false',
				'status_code': status_code,
				'message': _('User does not exist')
			}
		return Response(response, status=status_code)

class RequestResetForgottenPasswordView(viewsets.ModelViewSet):
	"""
	Endpoint for requesting resetting of forgotten password.
	It is different from the ChangePasswordView which takes care
	of normal updating of passwords
	"""
	serializer_class = RequestResetForgottenPasswordSerializer
	model = CustomUser
	# permission_classes = (IsAuthenticated, IsAdminOrSelf)

	def request_password_reset(self, request, *args, **kwargs):
		"""Request password change"""
		try:
			serializer = self.serializer_class(data=request.data, partial=True)
			if serializer.is_valid():
				email = request.data['email'] # self.kwargs.get('email', None) # self.request.query_params.get('uidb64', None)
				user = CustomUser.objects.get(email=email)
				self.send_reset_password_request_email(request, email)
		except(TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
			user = None
		
		if user is not None:
			status_code = status.HTTP_200_OK
			response = {
				'success': 'true',
				'status_code': status_code,
				'message': _('Please confirm password reset request from your email.'),
			}
		else:
			status_code = status.HTTP_400_BAD_REQUEST
			response = {
				'success': 'false',
				'status_code': status_code,
				'message': _('A user with the specified email does not exist'),
			}
		return Response(response, status=status_code)

	def send_reset_password_request_email(self, request, email_addr):
		"""Send an email"""
		current_site = get_current_site(request)
		user = CustomUser.objects.filter(email=email_addr).first()
		setts = get_settings()
		uid = urlsafe_base64_encode(force_bytes(user.pk))
		token = default_token_generator.make_token(user)

		message = render_to_string('user/change_password.html', {
				'user': user,
				'domain': current_site.domain,
				'uid': uid,
				'token': token,
				'endpoint': setts.change_password_url.rstrip("/") + "/" + uid + "/" + token + "/",
			})
		to_email = user.email
		subject = _("MISLAND Password Change Request")
		return email_helper.send_email(subject, message, [to_email])		
		
class ResetForgottenPasswordView(viewsets.ModelViewSet):
	"""
	View to manage activation of user accounts	
	"""
	# See https://medium.com/@frfahim/django-registration-with-confirmation-email-bb5da011e4ef

	serializer_class = ResetForgottenPasswordSerializer
	def reset_password(self, request, *args, **kwargs):
		"""Reset forgotten user password"""
		try:
			serializer = self.serializer_class(data=request.data, partial=True)
			if serializer.is_valid():
				uidb64 = serializer.validated_data['uid']# self.kwargs.get('uidb64', None) # self.request.query_params.get('uidb64', None)
				token = serializer.validated_data['token'] # self.kwargs.get('token', None) #self.request.query_params.get('token', None)
				password = serializer.validated_data['new_password']
				confirm_password = serializer.validated_data['confirm_password']
				uid = urlsafe_base64_decode(uidb64).decode()
				user = CustomUser.objects.get(pk=uid)
		except(TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
			user = None
		
		if user is not None and default_token_generator.check_token(user, token):			
			if serializer.data.get('new_password') != serializer.data.get('confirm_password'):
				status_code = status.HTTP_400_BAD_REQUEST
				response = {
					'success': 'false',
					'status_code': status_code,
					'message': _('Passwords do not match')
				}
				return Response(response, status=status_code)
			
			# set password
			user.set_password(serializer.data.get("new_password"))
			user.save()
			status_code = status.HTTP_200_OK
			response = {
				'success': 'true',
				'status_code': status_code,
				'message': _('Password updated successfully')
			}
			return Response(response, status_code)
		else:
			status_code = status.HTTP_400_BAD_REQUEST
			response = {
				'success': 'false',
				'status_code': status_code,
				'message': _('The reset password link is invalid'),
			}
		return Response(response, status=status_code)

class ChangePasswordView(generics.UpdateAPIView):
	"""
	Endpoint for changing password
	"""
	serializer_class = ChangePasswordSerializer
	model = CustomUser
	permission_classes = (IsAuthenticated, IsAdminOrSelf)

	def get_object(self, queryset=None, email=None):
		"""If no email supplied, return the current user"""
		if not email:
			obj = self.request.user
		else:
			obj = CustomUser.objects.filter(email=email).first()
		# Ensure that permission classes (IsAuthenticated, IsAdminOrSelf) are applied
		self.check_object_permissions(self.request, obj)
		return obj

	def post(self, request, *args, **kwargs):
		self.object = self.get_object(email=request.data.get('email'))
		serializer = self.get_serializer(data=request.data)

		if serializer.is_valid():
			# check if new passwords match
			if serializer.data.get('new_password') != serializer.data.get('confirm_password'):
				status_code = status.HTTP_400_BAD_REQUEST
				response = {
					'success': 'false',
					'status_code': status_code,
					'message': _('New passwords do not match')
				}
				return Response(response, status=status_code)
			# check old password
			if not self.object.check_password(serializer.data.get('old_password')):
				status_code = status.HTTP_400_BAD_REQUEST
				response = {
					'success': 'false',
					'status_code': status_code,
					'message': _('Incorrect old password')
				}
				return Response(response, status=status_code)
			
			# set password
			self.object.set_password(serializer.data.get("new_password"))
			self.object.save()
			status_code = status.HTTP_200_OK
			response = {
				'success': 'true',
				'status_code': status_code,
				'message': _('Password updated successfully')
			}
			return Response(response, status_code)

		return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserUpdateView(generics.UpdateAPIView):
	"""
	Endpoint for updating user
	"""
	serializer_class = UserUpdateSerializer
	# model = CustomUser
	permission_classes = (IsAuthenticated, IsAdminOrSelf)

	def get_object(self, queryset=None, email=None):		
		obj = CustomUser.objects.filter(email=email).first()
		# Ensure that permission classes (IsAuthenticated, IsAdminOrSelf) are applied
		self.check_object_permissions(self.request, obj)
		return obj

	def post(self, request, *args, **kwargs):
		self.object = self.get_object(email=request.data.get("email"))
		if not self.object:
			status_code = status.HTTP_400_BAD_REQUEST
			response = {
				'success': 'false',
				'status_code': status_code,
				'message': _('User does not exist')
			}
			return Response(response, status=status_code)

		"""If user is not admin, disable sensitive fields"""
		if not request.user.is_admin:
			request.data['is_admin'] = False
			request.data['is_superuser'] = False
			request.data['is_staff'] = False
			request.data['profile']['can_upload_custom_shapefile'] = False
			request.data['profile']['can_upload_standard_raster'] = False

		serializer = self.serializer_class(self.object, data=request.data, partial=True)
		if serializer.is_valid():
			serializer.save()
			status_code = status.HTTP_200_OK
			response = {
				'success': 'true',
				'status_code': status_code,
				'message': _('User details updated successfully')
			}
			return Response(response, status_code)

		return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
