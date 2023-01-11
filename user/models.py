from django.db import models
from django.utils.translation import gettext as _
from django.utils import timezone
from django.utils.http import urlquote
from django.core.mail import send_mail
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, PermissionsMixin
from django.contrib.auth import get_user_model


class CustomUserManager(BaseUserManager):
	"""Manager for a custom user model"""
	
	def _create_user(self, email, password, **extra_fields):
		"""
		Create and return a user `User` with an email, username and password
		"""
		if not email:
			raise ValueError(_('Users must have an email address'))
			
		extra_fields.pop("is_superuser", None)
		now = timezone.now()
		user = self.model(
			# username=self.normalize_email(email),
			email=self.normalize_email(email),
			# is_staff=is_staff,
			# is_admin=is_admin,
			is_superuser=False, # is_superuser. Superuser should be created only from Django Admin,
			# last_login=now,
			date_joined=now,
			**extra_fields
		)
		user.set_password(password)
		user.save(using=self._db)
		return user

	def create_user(self, email, password=None, **extra_fields):
		"""
		Create and return a `User` 
		"""
		if password is None:
			raise ValueError (_("Users must have a password"))
		return self._create_user(email, password, **extra_fields)
	
	def create_superuser(self, email, password=None, **extra_fields):
		"""
		Create and return a `User`. 
		"""
		
		if password is None:
			raise ValueError (_("Users must have a password"))
		user = self._create_user(email, password, **extra_fields) 
		user.is_staff=True
		user.is_admin=True
		user.is_superuser=True
		user.save(using=self._db)

class CustomUser(AbstractBaseUser, PermissionsMixin):
	"""Model for Custom User"""
	username = models.CharField(max_length=50, 
				unique=True,
				blank=True)
	email = models.EmailField(
		verbose_name=_('Email address'),
		max_length=255,
		unique=True,
		blank=False
	)
	first_name = models.CharField(max_length=50, unique=False)
	last_name = models.CharField(max_length=50, unique=False)
	is_active = models.BooleanField(_('active'), 
			  help_text=_('Designates whether this user should be treated as '
					'active. Unselect this instead of deleting accounts.'),
			  default=True)
	is_staff = models.BooleanField(_('staff status'),
			  help_text=_('Designates whether the user can log into this admin '
					'site.'), 
			  default=True)
	is_superuser = models.BooleanField(default=False)
	is_admin = models.BooleanField(default=False)
	date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
	password2 = models.CharField(max_length=255, blank=True, default="")
	
	USERNAME_FIELD = 'email'
	REQUIRED_FIELDS = []

	'''Tells DJango that the UserManager class defined above
	should manage objects of this type
	'''
	objects = CustomUserManager()

	def __str__(self):
		return self.email

	class Meta:
		'''
		to set table name in the database
		'''
		# db_table = 'user'
		# app_label = 'users'
		verbose_name = _('user')
		verbose_name_plural = _('users')

	def get_absolute_url(self):
		return "/users/%s/" % urlquote(self.email)

	def get_full_name(self):
		"""
		Returns the first_name plus the last_name, with a space in between.
		"""
		full_name = '%s %s' % (self.first_name, self.last_name)
		return full_name.strip()

	def get_short_name(self):
		"Returns the short name for the user."
		return self.first_name

	def email_user(self, subject, message, from_email=None):
		"""
		Sends an email to this User.
		"""
		send_mail(subject, message, from_email, [self.email])
		
class UserProfile(models.Model):
	"""
	Profile Model for user
	"""	
	user = models.OneToOneField(get_user_model(), on_delete=models.CASCADE, related_name='profile')
	profession = models.CharField(max_length=100)
	title = models.CharField(max_length=100)
	institution = models.CharField(max_length=100)
	can_upload_custom_shapefile = models.BooleanField(default=False)
	can_upload_standard_raster = models.BooleanField(default=False)
	
	class Meta:
		'''
		to set table name in the database
		'''        
		# db_table = 'userprofile'
		pass
