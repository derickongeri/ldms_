# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import datetime
# from django.db import models
from django.contrib.gis.db import models
from django.db.models.manager import Manager as GeoManager
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth import get_user_model
from ldms.enums import RasterSourceEnum, RasterCategoryEnum, ComputationEnum
from django.utils.translation import gettext as _
from django.utils import timezone
from django.template.defaultfilters import slugify

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
import os

User = get_user_model()

class ShapeFile(models.Model):
	"""
	Model to handle shapefiles
	"""
	filename = models.CharField(max_length=255)
	srs = models.CharField(max_length=254, blank=True)
	geom_type = models.CharField(max_length=50)
	encoding = models.CharField(max_length=20, blank=True)

	def __str__(self):
		return self.filename

class Attribute(models.Model):
	"""
	Model to handle shapefile attributes
	"""
	shapefile = models.ForeignKey(ShapeFile, on_delete=models.CASCADE)
	name = models.CharField(max_length=255)
	type = models.IntegerField()
	width = models.IntegerField()
	precision = models.IntegerField()

	def __str__(self):
		return 'Name: %s' % self.name

class Feature(models.Model):
	"""
	Model to handle features of a shapefile
	"""
	feature_name = models.CharField(max_length=255, default="")
	shapefile = models.ForeignKey(ShapeFile, on_delete=models.CASCADE)
	# geom_point = models.PointField(srid=4326, blank=True, null=True)
	# geom_multipoint = models.MultiPointField(srid=4326, blank=True, null=True)	
	# geom_linestring = models.LineStringField(srid=4326, blank=True, null=True)
	# geom_multilinestring = models.MultiLineStringField(srid=4326, blank=True, null=True)
	# geom_polygon = models.PolygonField(srid=4326, blank=True, null=True)
	# geom_multipolygon = models.MultiPolygonField(srid=4326, blank=True, null=True)
	geom_geometrycollection = models.GeometryCollectionField(srid=4326, blank=True, null=True)
	objects = GeoManager() #to allow for spatial queries and operations

class AttributeValue(models.Model):
	"""
	Model to handle attribute features of a shapefile
	"""
	feature = models.ForeignKey(Feature, on_delete=models.CASCADE)
	attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE)
	value = models.CharField(max_length=255, blank=True, null=True)

class RegionalAdminLevel(models.Model):
	"""
	Model for regional shapefile
	"""
	object_id = models.IntegerField(default=0)
	name = models.CharField(max_length=100, null=True, blank=True)
	shape_length = models.FloatField(blank=True, null=True, default=0)
	shape_area = models.FloatField(blank=True, null=True, default=0)
	geom = models.MultiPolygonField()
	objects = GeoManager() #to allow for spatial queries and operations
	# asap0_id = models.BigIntegerField()
	# name0 = models.CharField(max_length=100, blank=True, null=True)	
	# name0_shr = models.CharField(max_length=16, blank=True, null=True)	
	# asap_cntry = models.CharField(max_length=255, blank=True, null=True)	
	# an_crop	= models.CharField(max_length=255, blank=True, null=True)
	# an_range = models.CharField(max_length=255, blank=True, null=True)	
	# km2_tot = models.BigIntegerField(blank=True, null=True)	
	# km2_crop = models.BigIntegerField(blank=True, null=True)	
	# km2_rang2 = models.BigIntegerField(blank=True, null=True)	
	# g1_units = models.BigIntegerField(blank=True, null=True)	
	# isocode = models.CharField(max_length=2, blank=True, null=True)	
	# name = models.CharField(max_length=100, blank=True, null=True)
	# geom = models.MultiPolygonField()

	# objects = GeoManager() #to allow for spatial queries and operations

	# def __str__(self):
	# 	return self.name or self.object_id

class AdminLevelZero(models.Model):
	"""
	Model to handle Admin Level Zero boundaries
	"""
	gid_0 = models.CharField(max_length=50)
	name_0 = models.CharField(max_length=250)
	cpu = models.CharField(max_length=250, blank=True)
	geom = models.MultiPolygonField()

	objects = GeoManager() #to allow for spatial queries and operations

	def __str__(self):
		return self.name_0

class AdminLevelOne(models.Model):
	"""
	Model to handle Admin Level One boundaries
	"""
	admin_zero = models.ForeignKey(AdminLevelZero, on_delete=models.CASCADE)
	gid_0 = models.CharField(max_length=50)
	name_0 = models.CharField(max_length=250)	
	gid_1 = models.CharField(max_length=50)	
	name_1 = models.CharField(max_length=250)	
	varname_1 = models.CharField(max_length=250, blank=True)	
	nl_name_1 = models.CharField(max_length=250, blank=True)	
	type_1 = models.CharField(max_length=250, blank=True)	
	engtype_1 = models.CharField(max_length=250, blank=True)	
	cc_1 = models.CharField(max_length=50, default='', blank=True)	
	hasc_1 = models.CharField(max_length=250, blank=True)	
	cpu = models.CharField(max_length=250, blank=True)
	geom = models.MultiPolygonField()

	objects = GeoManager() #to allow for spatial queries and operations

	def __str__(self):
		return self.name_1

class AdminLevelTwo(models.Model):
	"""
	Model to handle Admin Level Two boundaries
	"""
	admin_one = models.ForeignKey(AdminLevelOne, on_delete=models.CASCADE)
	gid_0 = models.CharField(max_length=50)
	name_0 = models.CharField(max_length=250)
	gid_1 = models.CharField(max_length=250)
	name_1 = models.CharField(max_length=250)
	nl_name_1 = models.CharField(max_length=250, blank=True)
	gid_2 = models.CharField(max_length=250)
	name_2 = models.CharField(max_length=250)
	varname_2 = models.CharField(max_length=250, blank=True)
	nl_name_2 = models.CharField(max_length=250, blank=True)
	type_2 = models.CharField(max_length=250, blank=True)
	engtype_2 = models.CharField(max_length=250, blank=True)
	cc_2 = models.CharField(max_length=250, default='', blank=True)
	hasc_2 = models.CharField(max_length=250, blank=True)
	cpu = models.CharField(max_length=250, blank=True)
	geom = models.MultiPolygonField()

	objects = GeoManager() #to allow for spatial queries and operations


class RasterType(models.Model):
	"""
	Model for Raster Types
	"""
	name = models.CharField(max_length=250, blank=False)
	description = models.TextField(blank=True, null=True)
	
	def __str__(self):
		return "%s: %s" % (self.name, self.description)

def current_year():
	return datetime.date.today().year
	
def max_year_validator(value):
	return MaxValueValidator(current_year())(value)

class Raster(models.Model):
	"""
	Model to store Raster MetaData
	"""
	raster_types = (
		("LULC", 'Land Use/Land Cover'),
		("Productivity", 'Productivity'),
		("Carbon Stocks", 'Carbon Stocks'),
		("Land Degradation", 'Land Degradation'),
		('Ecological Units', 'Ecological Units'),
		("Forest Loss", 'Forest Loss'),
	)	
	RASTER_CATEGORIES = []	
	for itm in RasterCategoryEnum:
		RASTER_CATEGORIES.append((itm.value, itm.value))
	
	RASTER_SOURCES = []
	for itm in RasterSourceEnum:
		RASTER_SOURCES.append((itm.value, itm.value))

	name = models.CharField(max_length=100, blank=False, null=True)
	description = models.TextField(blank=True, null=True)
	raster_year = models.PositiveIntegerField(
			blank=False,
			default=current_year(),
			validators=[MinValueValidator, max_year_validator]
	)
	# raster_type = models.CharField(max_length=100, choices=raster_types, blank=True)
	raster_type = models.ForeignKey(RasterType, blank=True, null=True, on_delete=models.PROTECT)
	raster_category = models.CharField(max_length=100, choices=RASTER_CATEGORIES, blank=False, default="")
	# datatype = models.CharField(max_length=2, choices=DATATYPES, default='co')
	rasterfile = models.FileField(null=True, blank=False)
	raster_source = models.CharField(max_length=50, choices=RASTER_SOURCES, blank=False, default="")
	admin_zero = models.ForeignKey(AdminLevelZero, on_delete=models.CASCADE, default="", blank=True, null=True)
	resolution = models.FloatField(null=True, blank=True)
	# rasterlayer = models.OneToOneField(RasterLayer, related_name='metadata', on_delete=models.CASCADE)
	uperleftx = models.FloatField(null=True, blank=True)
	uperlefty = models.FloatField(null=True, blank=True)
	width = models.IntegerField(null=True, blank=True)
	height = models.IntegerField(null=True, blank=True)
	scalex = models.FloatField(null=True, blank=True)
	scaley = models.FloatField(null=True, blank=True)
	skewx = models.FloatField(null=True, blank=True)
	skewy = models.FloatField(null=True, blank=True)
	numbands = models.IntegerField(null=True, blank=True)
	srs_wkt = models.TextField(null=True, blank=True)
	srid = models.PositiveSmallIntegerField(null=True, blank=True)
	max_zoom = models.PositiveSmallIntegerField(null=True, blank=True)
	
	class Meta:
		ordering = ['name','raster_year']

	def __str__(self):
		return self.name

class RasterCache(models.Model):
	"""
	Model for caching analysis results
	"""
	payload = models.TextField(null=True, blank=True)
	

class RasterValueMapping(models.Model):
	"""
	Model for Mapping Raster pixel values with a label
	"""
	raster_type = models.ForeignKey(RasterType, on_delete=models.CASCADE)
	value = models.FloatField(blank=True, null=True)
	label = models.CharField(max_length=250, blank=True, null=True)
	color = models.CharField(max_length=50, default="#FF0000", blank=True, null=True)

	def __str__(self):
		return "%s mapping" % (self.raster_type.name)

class ScheduledTask(models.Model):
	"""Model to store info about an asynchronous task"""
	owner = models.CharField(max_length=128)
	created_on = models.DateTimeField(auto_now_add=True)
	name = models.CharField(max_length=128)
	job_id = models.CharField(max_length=128)
	result = models.TextField(blank=True, null=True)
	error = models.TextField(blank=True, null=True)
	method = models.CharField(max_length=128)
	args = models.TextField(blank=True, null=True)
	orig_args = models.TextField(blank=True, null=True, help_text=_("Original payload as passed by the user before modification"))
	request = models.TextField(blank=True, null=True)
	status = models.CharField(max_length=50)
	succeeded = models.BooleanField(default=False)
	completed_on = models.DateTimeField(blank=True, null=True)
	notified_owner = models.BooleanField(default=False)
	notified_on = models.DateTimeField(blank=True, null=True)

class SystemSettings(models.Model):
	"""Singleton Django Model
	Ensures there's always only one entry in the database, and can fix the
	table (by deleting extra entries) even if added via another mechanism.
	
	Also has a static load() method which always returns the object - from
	the database if possible, or a new empty (default) instance if the
	database is still empty. If your instance has sane defaults (recommended),
	you can use it immediately without worrying if it was saved to the
	database or not.
	
	Useful for things like system-wide user-editable settings.
	"""
	# frontend_port = models.IntegerField(blank=False, null=False, help_text=_("Server port for the front end"))
	enable_guest_user_limit = models.BooleanField(default=False, help_text=_("If checked, guest users will process polygons upto a specific polygon size"))
	guest_user_polygon_size_limit = models.FloatField(blank=False, help_text=_("Maximum size of polygon in hectares that anonymous users can process using the system"))
	enable_signedup_user_limit = models.BooleanField(default=False, help_text=_("If checked, Logged in users will process polygons upto a specific polygon size"))
	signedup_user_polygon_size_limit = models.FloatField(blank=False, default=1, help_text=_("Maximum size of polygon in hectares that Logged in users can process using the system"))
	enable_task_scheduling = models.BooleanField(help_text=_("If checked, user tasks will be scheduled"))
	enable_user_account_email_activation = models.BooleanField(help_text=_("If checked, users will activate their accounts via email"))
	email_host = models.CharField(max_length=255, help_text=_("Email server host"))
	email_from_name = models.CharField("Sender Name", max_length=255, blank=False, null=True,
			help_text=_("Sender Name"))
	email_from_address = models.CharField("Sender Address", max_length=255, blank=False, null=True, 
			help_text=_("Sender Email Address"))	
	email_host_user = models.CharField(max_length=255, help_text=_("Email server user"))
	email_host_password = models.CharField(max_length=255, help_text=_("Email server password"))
	email_host_protocol = models.CharField(max_length=20, choices=[("TLS", "TLS"), ("SSL", "SSL")], blank=True, default="TLS", help_text=_("Email protocol"))
	email_host_port = models.IntegerField(help_text=_("Email server port"))
	task_results_url = models.CharField(max_length=255, blank=False, default="http://0.0.0.0:8080/#/dashboard/results/", null=False, help_text=_("Url to redirect user when results of scheduled task are available. Task id will be appended at the end after /"))
	raster_clipping_algorithm = models.CharField(max_length=20, choices=[("All Touched", "All Touched"), ("Pixel Center", "Pixel Center")], blank=True, default="All Touched:", 
			help_text=_("""All Touched=Include a pixel in the mask if it touches any of the shapes.
				Pixel Center= Include a pixel only if its center is within one of the shapes"""))
	account_activation_url = models.CharField(max_length=255, blank=False, default="http://0.0.0.0:8080/#/dashboard/activate/", null=False, help_text=_("Url sent to user to activate his account. Uid and token will be appended to the url"))
	change_password_url = models.CharField(max_length=255, blank=False, default="http://0.0.0.0:8080/#/dashboard/forgotpassword/", null=False, help_text=_("Url sent to user to reset his password. Uid and token will be appended to the url"))
	enable_cache = models.BooleanField(default=True, blank=True, help_text=_("If enabled, results of computation will be cached for a period as specified by the cache limit field"))
	cache_limit = models.IntegerField(default=86400, help_text=_("Number of seconds that results will be cached."))
	override_backend_port = models.BooleanField(default=True, help_text=_("If checked, the system will override the default port and use the value of Backend port"))
	backend_url = models.CharField(_("Backend url"), max_length=255, default='http://127.0.0.1/', null=True, help_text=_("Url of the backend. Do NOT include the port"))
	backend_port = models.IntegerField(_("Backend port"), default=80, help_text=_("Port from which the system is served"))
	enable_tiles = models.BooleanField(default=False, blank=True, help_text=_("If enabled, a WMS link will be returned for all analysis to allow rendering of tiles"))
	 
	class Meta:
		abstract = False # True
		verbose_name_plural = "System Settings"

	def save(self, *args, **kwargs):
		"""
		Save object to the database. Removes all other entries if there
		are any.
		"""
		self.__class__.objects.exclude(id=self.id).delete()
		super(SystemSettings, self).save(*args, **kwargs)

	@classmethod
	def load(cls):
		"""
		Load object from the database. Failing that, create a new empty
		(default) instance of the object and return it (without saving it
		to the database).
		"""
		try:
			return cls.objects.get()
		except cls.DoesNotExist:
			return cls()

class Gallery(models.Model):
	"""
	Class to store images to show on the front end
	"""	
	image_name = models.CharField(max_length=255, blank=False, help_text=_("Name of image"))
	image_file = models.FileField(max_length=255, blank=False, help_text=_("Attach image"))
	image_desc = models.TextField(blank=True, help_text=_("Image description"))
	is_published = models.BooleanField(help_text=_("If not published, the image will not be shown to users"))

	class Meta:
		verbose_name_plural = "Gallery"

class Topic(models.Model):
	"""
	Generic topics for grouping FAQ
	"""
	topic_name = models.CharField(blank=False, max_length=255)
	slug = models.SlugField(max_length=255)
	sort_order = models.IntegerField(default=0, verbose_name=_("Sort order"), 
							help_text=_("The order you would like the topic to be displayed"))

	def get_absolute_url(self):
		return '/faq/' + self.slug

	class Meta:
		verbose_name = _("Topic")
		verbose_name_plural = _("Topics")
		ordering = ['sort_order', 'topic_name']

	def __unicode__(self):
		return self.topic_name
	
	def __str__(self):
		return self.topic_name

class Question(models.Model):
	INACTIVE = 0
	ACTIVE = 1
	HEADER = 2

	STATUS_CHOICES = (
		(ACTIVE, _("Active")),
		(INACTIVE, _("Inactive")),
		(HEADER, _("Group Header")),
	)
	question_text = models.TextField(_("question"), help_text="The question details")
	answer = models.TextField(_("answer"), blank=True, help_text=_("The answer text"))
	topic = models.ForeignKey(Topic, verbose_name=_("topic"), related_name="questions", on_delete=models.CASCADE)
	slug = models.SlugField(_("slug"), max_length=100, blank=True, null=True)
	status = models.IntegerField(_("status"), choices=STATUS_CHOICES,
								default=INACTIVE,
								help_text=_("Only questions with their status set to 'Active' will be "
											"displayed. Questions marked as 'Group Header are treated as "
											"views"
								))
	protected = models.BooleanField(_('is protected'), default=False,
				help_text=_("Set true if this question is only visible to authenticated users"))
	sort_order = models.IntegerField(default=0, verbose_name=_("Sort order"),
							 help_text=_("The order you would like this question to be displayed"))
	created_on = models.DateTimeField(_('created on'), default=timezone.now)
	updated_on = models.DateTimeField(_('updated on'), blank=True, null=True, default=timezone.now)
	created_by = models.ForeignKey(User, verbose_name=_('created by'), blank=True,
									null=True, related_name="+", on_delete=models.CASCADE)
	updated_by = models.ForeignKey(User, verbose_name=_('updated by'), blank=True,
									null=True, related_name="+", on_delete=models.CASCADE)

	def save(self, *args, **kwargs):
		# Set date updated
		self.updated_on = timezone.now()

		# create a unique slug
		if not self.slug:
			suffix = 0
			potential = base = slugify(self.question_text[:90])
			while not self.slug:
				if suffix:
					potential = "%s-%s" % (base, suffix)
				if not Question.objects.filter(slug=potential).exists():
					self.slug = potential
				# We hit a conflicting slug; increment suffix and try again
				suffix += 1
		
		super(Question, self).save(*args, **kwargs)

	def is_header(self):
		return self.status == Question.HEADER

	def is_active(self):
		return self.status == Question.ACTIVE

class ComputationThreshold(models.Model):
	"""
	Class to store Thresholds for analysis
	"""
	RASTER_SOURCES = []
	for itm in RasterSourceEnum:
		RASTER_SOURCES.append((itm.value, itm.value))

	datasource = models.CharField(max_length=255, blank=False, null=False, choices=RASTER_SOURCES, unique=True)
	guest_user_threshold = models.FloatField(blank=False, help_text=_("Maximum size of polygon in hectares that anonymous users can process using the system for the selected datasource"))
	enable_guest_user_limit = models.BooleanField(default=True, help_text=_("If checked, guest users will process polygons upto a specific polygon size"))
	authenticated_user_threshold = models.FloatField(blank=False, help_text=_("Maximum size of polygon in hectares that anonymous users can process using the system for the selected datasource"))
	enable_signedup_user_limit = models.BooleanField(default=True, help_text=_("If checked, Logged in users will process polygons upto a specific polygon size"))
	
class CustomShapeFile(models.Model):
	"""
	Model for custom shape files
	"""
	owner = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
	shapefile_name = models.CharField(_("Description of the vector"), max_length=100, null=True, blank=True)
	# description = models.TextField(_("Description of the vector"), blank=False)
	shapefile = models.FileField(_("Upload Shapefile"))
	shape_length = models.FloatField(blank=True, null=True, default=0)
	shape_area = models.FloatField(blank=True, null=True, default=0)	
	# geom = models.MultiPolygonField()
	geom = models.GeometryCollectionField(srid=4326, blank=True, null=True)
	objects = GeoManager() #to allow for spatial queries and operations


@receiver(pre_save, sender=CustomShapeFile)
def load_shapefile_to_db(sender, instance, **kwargs):
	"""
	Extract GeoJSON from the uploaded shapefile
	"""
	# load shapefile to db
	# import the shapefile into the database
	from ldms.utils.file_util import (file_exists, get_absolute_media_path)
	from ldms.utils.vector_util import read_shapefile, delete_shapefile
	if instance.id is None: # new record
		if instance.shapefile:
			#instance.geom = read_shapefile(instance.shapefile)	
			instance.geom = read_shapefile(instance.shapefile.path)				
	else: # record is being updated
		current = instance
		previous = CustomShapeFile.objects.get(id=instance.id)

		#Only read file if another one has been uploaded
		if current.shapefile != previous.shapefile: 
			instance.geom = read_shapefile(instance.shapefile)	

@receiver(post_save, sender=CustomShapeFile)
def delete_uploaded_shapefile(sender, instance, created, **kwargs):
	"""
	Delete uploaded shapefile
	"""
	os.remove(instance.shapefile.path)# delete the uploaded file

class PublishedComputation(models.Model):
	class Meta:
		abstract = False # True
		verbose_name_plural = "Published Computations"

	def __str__(self):
		return self.computation_type

	COMPUTATIONS = []	
	for itm in ComputationEnum:
		COMPUTATIONS.append((itm.value, itm.value))
	 	
	computation_type = models.CharField(max_length=100, choices=COMPUTATIONS, blank=False, default="")
	style = models.TextField(help_text=_("Styled Layer Descriptor (SLD)"), null=True, blank=True)
	admin_zero = models.ForeignKey(AdminLevelZero, on_delete=models.CASCADE, 
					default="", blank=True, null=True, help_text=_("Associated country. Leave blank to associate with all countries"))
	published = models.BooleanField(default=True, null=True, help_text=_("If checked, only the specified years will be enabled for computation"))
	
	# created_on = models.DateTimeField(_('created on'), default=timezone.now)
	# updated_on = models.DateTimeField(_('updated on'), blank=True, null=True, default=timezone.now)
	# created_by = models.ForeignKey(User, verbose_name=_('created by'), blank=True,
	# 								null=True, related_name="+", on_delete=models.CASCADE)
	# updated_by = models.ForeignKey(User, verbose_name=_('updated by'), blank=True,
	# 								null=True, related_name="+", on_delete=models.CASCADE)

class PublishedComputationYear(models.Model):	
	published_computation = models.ForeignKey(PublishedComputation, verbose_name=_("published_computation"), related_name="published_computations", on_delete=models.CASCADE)
	published_year = models.PositiveIntegerField(
			blank=False,
			default=current_year(),
			validators=[MinValueValidator, max_year_validator]
	)

class DataImportSettings(models.Model):
	"""Singleton Django Model
	Ensures there's always only one entry in the database, and can fix the
	table (by deleting extra entries) even if added via another mechanism.
	
	Also has a static load() method which always returns the object - from
	the database if possible, or a new empty (default) instance if the
	database is still empty. If your instance has sane defaults (recommended),
	you can use it immediately without worrying if it was saved to the
	database or not.
	
	Useful for things like system-wide user-editable settings.
	"""	
	raster_data_file = models.FileField(help_text=_("JSON file that contains definition of rasters to be imported into the system from disk"))

	class Meta:
		abstract = False # True
		verbose_name_plural = "Data Import Settings"

	def save(self, *args, **kwargs):
		"""
		Save object to the database. Removes all other entries if there
		are any.
		"""
		self.__class__.objects.exclude(id=self.id).delete()
		super(DataImportSettings, self).save(*args, **kwargs)

	@classmethod
	def load(cls):
		"""
		Load object from the database. Failing that, create a new empty
		(default) instance of the object and return it (without saving it
		to the database).
		"""
		try:
			return cls.objects.get()
		except cls.DoesNotExist:
			return cls()