from django.test import TestCase
from django.urls import include, path
from user.models import CustomUser, UserProfile
from rest_framework import status
from rest_framework.test import APITestCase, RequestsClient, URLPatternsTestCase 
from django.contrib.gis.geos import GEOSGeometry
import json
import string
import random
from requests.auth import HTTPBasicAuth

class AuthenticationTests(APITestCase):

	def setUp(self):
		# initialize endpoints
		self.ENDPOINTS = {
			"login": self.get_url("login/"),
			"signup": self.get_url("signup/"),
			"updateuser": self.get_url("updateuser/"),
			"changepassword": self.get_url("changepwd/"),
			"user": self.get_url("user/"),
			"userlist": self.get_url("users/"),
		}

	def get_url(self, endpoint):
		return 'http://0.0.0.0:8000/api/%s' % (endpoint)

	def create_user(self, is_admin):
		email = "{0}@test.com".format(get_random_string(10, 0))
		data = {    
			"email": email,
			"username": email,
			"first_name": get_random_string(10, 1),
			"last_name": get_random_string(10, 1),
			"is_superuser": False,
			"is_admin": is_admin,
			"is_active": True,
			"password": "123",
		}
		user = CustomUser.objects.create(**data)
		user.set_password("123")
		user.save()

		UserProfile.objects.create(
			user=user,
			profession=get_random_string(10, 1),
			title=get_random_string(5, 1),
			institution=get_random_string(10, 1)
		)
		return user

	def authenticate(self, email=None, pwd=None):
		"""Login and get a token. If no email is passed, a new user is created"""
		if not email:
			user = self.create_user()
			email = user.email
			pwd = "123"

		# login with the user just created
		response = self.client.post(self.ENDPOINTS["login"], 
					data= { 
						"email": email, 
						"password": pwd
					}, 
					format='json')

		self.assertEqual(response.status_code, status.HTTP_200_OK)

		# extract token
		obj = json.loads(response.content)
		auth_token = obj['token']
	
		# Send a POST request but this time with the auth_token
		self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + auth_token)

	def test_login(self):
		"""
		Test user can login and token generated. 
		We expect a response as below : 
		{
			"success": "true",
			"status_code": 200,
			"message": "User logged in successfully",
			"token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxLCJ1c2VybmFtZSI6ImFkbWluQGFkbWluLmNvbSIsImV4cCI6MTYwNDczMzg3MCwiZW1haWwiOiJhZG1pbkBhZG1pbi5jb20ifQ.ejVR_oBiLuChPLLipAxrUavv4mSWO-4Wk7RN9sbJUJg"
		}		
		"""
		url = self.ENDPOINTS["login"]
		user = self.create_user(False)

		response = self.client.post(url, data={
				"email": user.email,
				"password": "123"
			}, format='json')

		self.assertEqual(response.status_code, status.HTTP_200_OK)

		obj = json.loads(response.content)
		
		# check that the objects are serialized and returned with correct keys
		self.assertEqual(obj.get('success'), "true")
		self.assertEqual(obj.get('status_code'), status.HTTP_200_OK)
		self.assertGreater(len(obj.get('token')), 0)

	def test_create_user(self):
		"""
		Test user can be created by anyone.

		We expect a response of the form
		response = {
			'success': 'true',
			'status_code': 201,
			'message': _('User registered successfully')
		}
		"""
		data = {
			"first_name": "Dummy F",
			"last_name": "Dummy L",
			"email": "humptydumpty@monkey.com",
			"password": "123",
			"password2": "123",
			"is_staff": True,
			"is_superuser": True,
			"is_admin": True,
			"profile": {
				"profession": "I.T",
				"institution": "IAT",
				"title": "Dr.",
				"can_upload_custom_shapefile": True,
				"can_upload_standard_raster": True
			}
		}
		url = self.ENDPOINTS["signup"] 

		response = self.client.post(url, data=data, format='json')
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)

		obj = json.loads(response.content)
		
		# check that the objects are serialized and returned with correct keys
		self.assertEqual(obj.get('success'), "true")
		self.assertEqual(obj.get('status_code'), status.HTTP_201_CREATED)

		# Check that the user was saved in the db
		user = CustomUser.objects.get(email="humptydumpty@monkey.com")

		self.assertEquals(user.first_name, data['first_name'])
		self.assertEquals(user.last_name, data['last_name'])
		self.assertEquals(user.email, data['email'])
		self.assertEquals(user.username, data['email'])
		self.assertEquals(user.is_active, True)
		self.assertEquals(user.check_password("123"), True) #check password well saved
		
		# Ensure that is_admin, is_superuser and is_staff are not set on user creation. 
		# They have to be assigned by an admin
		# in an update process
		self.assertEquals(user.is_admin, False)
		self.assertEquals(user.is_superuser, False)
		self.assertEquals(user.is_staff, False)
		
		# check profile
		profile = data['profile']
		self.assertEquals(user.profile.profession, profile['profession'])
		self.assertEquals(user.profile.institution, profile['institution'])
		self.assertEquals(user.profile.title, profile['title'])

		# Ensure that can_upload_custom_shapefile and can_upload_standard_raster
		# are not set on user creation. They have to be assigned by an admin
		# in an update process
		self.assertEquals(user.profile.can_upload_custom_shapefile, False)
		self.assertEquals(user.profile.can_upload_standard_raster, False)

	def test_update_user_by_unauthenticated_user(self):
		"""
		Test update of user details when the current is not logged in.
		We expect a HTTP_403_FORBIDDEN error
		"""
		user = self.create_user(is_admin=False)
		data = {
			"email": user.email,
			"first_name": "Dummy F",
			"last_name": "Dummy L",
			"is_active": 0,
			"is_superuser": 1,
			"is_admin": 1,
			"profile": {
				"profession": "Support",
				"institution": "Twitter",
				"title": "Professor",
				"can_upload_custom_shapefile": 1, 
				"can_upload_standard_raster": 1
			}
		}

		response = self.client.post(self.ENDPOINTS["updateuser"], 
									data=data, 
									format='json')

		# since we are unauthenticated yet, we should get a HTTP_403_FORBIDDEN error
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)		

	def test_update_user_by_current_user(self):
		"""
		Test update of user details when the current logged in user 
		is updating his details.

		We expect the response to be of this form:
		{
			"success": "true",
			"status_code": 200,
			"message": "User details updated successfully"
		}
		"""
		user = self.create_user(is_admin=False)
		data = {
			"email": user.email,
			"first_name": "Dummy F",
			"last_name": "Dummy L",
			"is_active": 0,
			"is_superuser": 0,
			"is_admin": 0,
			"password": "123",
			"profile": {
				"profession": "Support",
				"institution": "Twitter",
				"title": "Professor",
				"can_upload_custom_shapefile": 0, 
				"can_upload_standard_raster": 0
			}
		}

		# login with the user just created
		self.authenticate(email=user.email, pwd="123")
		# Send a POST request but this time with the auth_token set
		response = self.client.post(self.ENDPOINTS["updateuser"], 
									data=data, 
									format='json')

		self.assertEqual(response.status_code, status.HTTP_200_OK)

		obj = json.loads(response.content)
		
		# check that the objects are serialized and returned with correct keys
		self.assertEqual(obj.get('success'), "true")
		self.assertEqual(obj.get('status_code'), status.HTTP_200_OK)

		# Check that the user was saved in the db		
		self.validate_updated_user_details(email=user.email, expected_vals=data)

	def test_update_user_by_superuser(self):
		"""Test update of user details by the superuser.

		We expect the response to be of this form:
		{
			"success": "true",
			"status_code": 200,
			"message": "User details updated successfully"
		}
		"""
		superuser = self.create_user(is_admin=True)
		user = self.create_user(is_admin=False)
		data = {
			"email": user.email,
			"first_name": "Dummy F",
			"last_name": "Dummy L",
			"is_active": 0,
			"is_superuser": 1,
			"is_admin": 1,
			"password": "123",
			"profile": {
				"profession": "Support",
				"institution": "Twitter",
				"title": "Professor",
				"can_upload_custom_shapefile": 1, 
				"can_upload_standard_raster": 1
			}
		}

		# login with the superuser
		self.authenticate(email=superuser.email, pwd="123")
		# Send a POST request but this time with the auth_token set
		response = self.client.post(self.ENDPOINTS["updateuser"], 
									data=data, 
									format='json')

		self.assertEqual(response.status_code, status.HTTP_200_OK)

		obj = json.loads(response.content)
		
		# check that the objects are serialized and returned with correct keys
		self.assertEqual(obj.get('success'), "true")
		self.assertEqual(obj.get('status_code'), status.HTTP_200_OK)

		# Check that the user was saved in the db		
		self.validate_updated_user_details(email=user.email, expected_vals=data)
	
	def test_update_user_by_non_superuser_user(self):
		"""
		Test update of user details when the current logged in user 
		is not superuser and is trying to update another user details.
		We expect a HTTP_403_FORBIDDEN error
		"""
		non_superuser = self.create_user(is_admin=False) 
		user = self.create_user(is_admin=False)
		data = {
			"email": user.email,
			"first_name": "Dummy F",
			"last_name": "Dummy L",
			"is_active": 0,
			"is_superuser": 0,
			"is_admin": 1,
			"password": "123",
			"profile": {
				"profession": "Support",
				"institution": "Twitter",
				"title": "Professor",
				"can_upload_custom_shapefile": 1, 
				"can_upload_standard_raster": 1
			}
		}

		# login with the non superuser
		self.authenticate(email=non_superuser.email, pwd="123")
		# Send a POST request but this time with the auth_token set
		response = self.client.post(self.ENDPOINTS["updateuser"], 
									data=data, 
									format='json')
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def validate_updated_user_details(self, email, expected_vals):
		"""
		Check that user details were updated

		Args:
			email: Email of the created user
			expected_vals: Dict of expected values
		"""
		# Check that the user was saved in the db
		user = CustomUser.objects.get(email=email)

		self.assertEquals(user.first_name, expected_vals['first_name'])
		self.assertEquals(user.last_name, expected_vals['last_name'])
		self.assertEquals(user.email, expected_vals['email'])
		self.assertEquals(user.username, expected_vals['email'])
		self.assertEquals(user.is_active, expected_vals['is_active'])
		self.assertEquals(user.is_superuser, expected_vals['is_superuser'])
		self.assertEquals(user.is_admin, expected_vals['is_admin'])
		self.assertEquals(user.check_password(expected_vals['password']), True) #check password is retained

		# check profile
		profile = expected_vals['profile']
		self.assertEquals(user.profile.profession, profile['profession'])
		self.assertEquals(user.profile.institution, profile['institution'])
		self.assertEquals(user.profile.title, profile['title'])
		self.assertEquals(user.profile.can_upload_custom_shapefile, profile['can_upload_custom_shapefile'])
		self.assertEquals(user.profile.can_upload_standard_raster, profile['can_upload_standard_raster'])

	def test_change_password_by_owner(self):
		"""Test password can be changed the owner
		We expect the response to be of this form:
		{
			"success": "true",
			"status_code": 200,
			"message": "Password updated successfully"
		}
		"""
		user = self.create_user(is_admin=False)		
		data = {
			"email": user.email,
			"old_password": "123",
			"new_password": "456",
			"confirm_password": "456"
		}

		# login with the user just created
		self.authenticate(email=user.email, pwd="123")
		# Send a POST request but this time with the auth_token set
		response = self.client.post(self.ENDPOINTS["changepassword"], 
									data=data, 
									format='json')
		self.assertEqual(response.status_code, status.HTTP_200_OK)

		obj = json.loads(response.content)
		
		# check that the objects are serialized and returned with correct keys
		self.assertEqual(obj.get('success'), "true")
		self.assertEqual(obj.get('status_code'), status.HTTP_200_OK)

		# Check that the user was saved in the db
		user = CustomUser.objects.get(email=user.email)

		 #check password is updated
		self.assertEquals(user.check_password("456"), True)

	def test_change_password_by_superuser(self):
		"""Test password can be changed by a super admin
		We expect the response to be of this form:
		{
			"success": "true",
			"status_code": 200,
			"message": "Password updated successfully"
		}
		"""
		superuser = self.create_user(is_admin=True)
		user = self.create_user(is_admin=False)		
		data = {
			"email": user.email,
			"old_password": "123",
			"new_password": "456",
			"confirm_password": "456"
		}
		# login with the superuser
		self.authenticate(email=superuser.email, pwd="123")
		
		# Send a POST request but this time with the auth_token set
		response = self.client.post(self.ENDPOINTS["changepassword"], 
									data=data, 
									format='json')
		self.assertEqual(response.status_code, status.HTTP_200_OK)

		obj = json.loads(response.content)
		
		# check that the objects are serialized and returned with correct keys
		self.assertEqual(obj.get('success'), "true")
		self.assertEqual(obj.get('status_code'), status.HTTP_200_OK)

		# Check that the user was saved in the db
		user = CustomUser.objects.get(email=user.email)

		#check password is updated
		self.assertEquals(user.check_password("456"), True)

	def test_change_password_by_non_superuser_user(self):
		"""Test password cannot be changed by anyone except the 'owner' or a super admin
		We expect a HTTP_403_FORBIDDEN error
		"""
		non_superuser = self.create_user(is_admin=False)
		user = self.create_user(is_admin=False)		
		data = {
			"email": user.email,
			"old_password": "123",
			"new_password": "456",
			"confirm_password": "456"
		}
		# login with the non superuser
		self.authenticate(email=non_superuser.email, pwd="123")
		
		# Send a POST request but this time with the auth_token set
		response = self.client.post(self.ENDPOINTS["changepassword"], 
									data=data, 
									format='json')
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_change_passwords_with_mismatch(self):
		"""Test password change with the confirm password field mismatch
		We expect a HTTP_400_BAD_REQUEST error
		We expect the response to be of this form:
		{
			"success": "false",
			"status_code": 400,
			"message": "New passwords do not match"
		}
		"""
		user = self.create_user(is_admin=False)		
		data = {
			"email": user.email,
			"old_password": "123",
			"new_password": "456",
			"confirm_password": "4589"
		}
		# login with the non superuser
		self.authenticate(email=user.email, pwd="123")
		
		# Send a POST request but this time with the auth_token set
		response = self.client.post(self.ENDPOINTS["changepassword"], 
									data=data, 
									format='json')
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_get_user_list_by_superuser(self):
		"""
		Test only superuser can get list of users
		"""
		user = self.create_user(is_admin=False)
		another_user = self.create_user(is_admin=False)
		superuser = self.create_user(is_admin=True)
		
		# login with the superuser
		self.authenticate(email=superuser.email, pwd="123")
		
		# Send a POST request but this time with the auth_token set
		response = self.client.get(self.ENDPOINTS["userlist"], 
									data=None, 
									format='json')

		self.assertEqual(response.status_code, status.HTTP_200_OK)

		obj = json.loads(response.content)

		# verify that all the users will be returned
		self.assertEqual(len(obj), 3)

	def test_get_user_list_by_non_superuser(self):
		"""
		Test non-superusers cannot get list of users
		"""
		user = self.create_user(is_admin=False)
		another_user = self.create_user(is_admin=False)
		superuser = self.create_user(is_admin=True)
		
		# login with the non superuser
		self.authenticate(email=user.email, pwd="123")
		
		# Send a POST request but this time with the auth_token set
		response = self.client.get(self.ENDPOINTS["userlist"], 
									data=None, 
									format='json')

		self.assertEqual(response.status_code, status.HTTP_200_OK)

		obj = json.loads(response.content)
		# verify that only one user is returned while the rest are excluded
		self.assertEqual(len(obj), 1)

	def test_retrieve_user_by_owner(self):
		"""Test that a non superuser can only retrieve the current user details
		We expect an object of this form containing only one user in the data section
		{
			"success": "true",
			"status_code": 200,
			"message": "User profile fetched successfully",
			"data": [
				{
					"email": "admin@admin.com",
					"first_name": "Administrator",
					"last_name": "Admin",
					"profession": "IT",
					"institution": "World Bank",
					"title": "Dr",
					"is_active": 1,
					"is_admin": 1,
					"can_upload_custom_shapefile": 0,
					"can_upload_standard_raster": 0
				}
			]
		}
		"""
		superuser = self.create_user(is_admin=True)
		user = self.create_user(is_admin=False)	
		another_user = self.create_user(is_admin=False)		
		
		# login with the user
		self.authenticate(email=user.email, pwd="123")
		
		# Send a GET request but this time with the auth_token set
		response = self.client.get(self.ENDPOINTS["user"], 
									data=None, 
									format='json')
		self.assertEqual(response.status_code, status.HTTP_200_OK)

		obj = json.loads(response.content)
		
		# check that the objects are serialized and returned with correct keys
		self.assertEqual(obj.get('success'), "true")
		self.assertEqual(obj.get('status_code'), status.HTTP_200_OK)

		# Check that only the current user was retrieved
		self.assertEqual(len(obj.get('data')), 1) 

		user_obj = obj['data'][0]
		self.assertEqual(user_obj.get('email'), user.email)
		self.assertEqual(user_obj.get('first_name'), user.first_name)

	def test_retrieve_user_by_superuser(self):
		"""Test superuser can retrieve another user details
		We expect all the users to be returned
		"""
		superuser = self.create_user(is_admin=True)
		user = self.create_user(is_admin=False)	 
		
		# login with the user
		self.authenticate(email=superuser.email, pwd="123")
		
		# Send a GET request but this time with the auth_token set
		response = self.client.get(self.ENDPOINTS["user"] + "?email="+user.email, 
									data=None, 
									format='json')
		self.assertEqual(response.status_code, status.HTTP_200_OK)

		obj = json.loads(response.content)
		
		# check that the objects are serialized and returned with correct keys
		self.assertEqual(obj.get('success'), "true")
		self.assertEqual(obj.get('status_code'), status.HTTP_200_OK)

		# Check that only the user was retrieved
		self.assertEqual(len(obj.get('data')), 1) 

		user_obj = obj['data'][0]
		self.assertEqual(user_obj.get('email'), user.email)
		self.assertEqual(user_obj.get('first_name'), user.first_name)

	def test_retrieve_another_user_by_non_superuser_user(self):
		"""
		Test nonsuperuser cannot retrieve another user details.
		We expect a HTTP_403_FORBIDDEN error
		"""
		non_superuser = self.create_user(is_admin=False)
		user = self.create_user(is_admin=False)	 
		
		# login with the user
		self.authenticate(email=non_superuser.email, pwd="123")
		
		# Send a GET request but this time with the auth_token set
		response = self.client.get(self.ENDPOINTS["user"] + "?email="+user.email, 
									data=None, 
									format='json')
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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