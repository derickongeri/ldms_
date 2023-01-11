from ldms.models import Raster
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.gis.gdal import GDALRaster
from django.conf import settings
from ldms.utils.file_util import file_exists, get_media_dir
from pathlib import Path
from ldms.utils.raster_util import get_raster_object 

# from cmdbox.profiles.models import Profile

# @receiver(post_save, sender=Raster)
# def create_user_profile(sender, instance, created, **kwargs):
#     if created:
#         Profile.objects.create(user=instance)

@receiver(post_save, sender=Raster)
def generate_raster_metadata(sender, instance, **kwargs):
	"""
	Generate Raster Meta data
	"""
	if not instance.rasterfile:
		return
	file_path = get_media_dir() + instance.rasterfile.name
	if file_exists(file_path, raise_exception=False):
		rst = get_raster_object(file_path)
		vals = {
			"uperleftx" : rst.origin.x, 
			"uperlefty" : rst.origin.y, 
			"width" : rst.width, 
			"height" : rst.height, 
			"scalex" : rst.scale.x, 
			"scaley" : rst.scale.y, 
			"skewx" : rst.skew.x, 
			"skewy" : rst.skew.y, 
			"numbands" : len(rst.bands), 
			"srs_wkt" : rst.srs.wkt, 
			"srid" : rst.srs.srid, 
			# "max_zoom" : rst.x
		}
		Raster.objects.filter(id=instance.id).update(**vals)