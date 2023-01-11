import jwt
from django.conf import settings
from rest_framework import authentication, exceptions
from django.utils.translation import gettext as _
from django.contrib.auth import get_user_model

User = get_user_model()

class JWTAuthentication(authentication.BaseAuthentication):
	"""
	Custom backend to support JWT since this 
	is not supported by Django nor Django REST Framework(DRF) by default
	"""
	authentication_header_prefix = 'Bearer' # 'Token'

	def authenticate(self, request):
		"""
		The `authenticate` method is called on every request
		regardless of whether the endpoint requires authentication.

		`authenticate` has two possible return values:

		1) `None` - We return `None` if we do not wish to authenticate.
					Usually this means we know authentication will fail. An
					example is when the request does not include a token
					in the headers.

		2) `(user, token)` - We return a user/token combination when
							 authentication is successful.

		If neither case is met, that means there is an error and we do not
		return anything. We simply raise the `AuthenticationFailed` exception
		and let Django REST Framework handle the rest.
		"""
		request.user = None

		"""
		`auth_header` should be an array with two elements: 
			1) the name of the authentication header (in this case, "Token")
			2) the JWT that we should authenticate against
		"""

		auth_header = authentication.get_authorization_header(request).split()
		auth_header_prefix = self.authentication_header_prefix.lower()

		if not auth_header:
			return None
		
		if len(auth_header) == 1:
			"""
			Invalid token header. No credentials provided. Do not attempt
			to authenticate
			"""
			return None
		elif len(auth_header) > 2:
			"""
			Invalid token header. The Token string should not contain
			spaces. Do not attempt to authenticate
			"""
			return None

		"""
		Some JWT library version cannot handle the `byte` type which is 
		commonly used by standard libraries in Python 3. To get around this,
		we decode `prefix` and `token`.
		"""
		prefix = auth_header[0].decode('utf-8')
		token = auth_header[1].decode('utf-8')

		if prefix.lower() != auth_header_prefix:
			"""
			If the auth_header prefix is not what we expect it to be,
			do not attempt to authenticate 
			"""
			return None

		return self._authenticate_credentials(request, token)

	def _authenticate_credentials(self, request, token):
		"""
		Try to authenticate the given credentials. If authentication is 
		successful, return the user and token. If not, throw an error
		"""
		try:
			payload = jwt.decode(token, settings.SECRET_KEY)
		except:
			msg = _('Invalid authentication. Could not decode token')
			raise exceptions.AuthenticationFailed(msg)

		try:
			user = User.objects.get(pk=payload['user_id'])
		except User.DoesNotExist:
			msg = _('No user matching this token was found.')
			raise exceptions.AuthenticationFailed(msg)

		if not user.is_active:
			msg = _("This user has been deactivated.")
			raise exceptions.AuthenticationFailed(msg)

		return (user, token)