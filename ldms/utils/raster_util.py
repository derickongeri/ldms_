from ldms.utils.file_util import get_physical_file_path_from_url
from operator import mod
from django.db.models.fields import FilePathField
from rasterio import windows
import rasterstats 
from django.utils.translation import gettext as _
import geopandas as gpd
from ldms.utils.file_util import (file_exists, get_absolute_media_path, 
			get_media_dir, get_download_url, get_temp_file)
from ldms.models import Raster, RasterType, SystemSettings
from django.conf import settings
from django.contrib.gis.gdal import GDALRaster
import rasterio
from rasterio.transform import from_origin
import numpy as np
import numpy.ma as ma
import fiona
import rasterio
import rasterio.mask
from rasterio.enums import Resampling
from rasterio.windows import Window
from rasterio.warp import calculate_default_transform, reproject, Resampling
import tempfile
import json

from ldms import AnalysisParamError
from ldms.models import RegionalAdminLevel, AdminLevelTwo, AdminLevelZero
from ldms.enums import RasterSourceEnum, GenericRasterBandEnum, MODISBandEnum, \
	Landsat7BandEnum, Landsat8BandEnum, RasterOperationEnum, RasterCategoryEnum
from ldms.utils.common_util import cint, list_to_queryset
from ldms.utils.settings_util import get_settings
from ldms.models import Raster
from ldms.utils.geoserver_util import GeoServerHelper

class RasterCalcHelper():   
	"""
	Helper Class to compute Raster statistics using vector geometries

	Call `get_stats` method to get computed statistics

	Referenced as `RasterCalcHelper().get_stats()`
	
	# TODO: validate the Geometry passed
	# TODO: Optimize for large images
	# TODO: Test that raster extent falls within the vector. Check https://www.earthdatascience.org/courses/use-data-open-source-python/spatial-data-applications/lidar-remote-sensing-uncertainty/extract-data-from-raster/
	"""

	def __init__(self, 
				vector, 
				rasters, 
				raster_type_id, 
				stats=None, 
				is_categorical=True, 
				transform="x",                
				raster_resolution=None):
		"""
		Initialize instance values
		
		Args:
			shapefile:
				Vector data to use to overlay raster on. Either of: 
					- Shapefile path 
					- Geometry either of ["Point", "LineString", "Polygon",
						"MultiPoint", "MultiLineString", "MultiPolygon"]
			rasters (list<Raster>): 
				List of Raster Models
			
			raster_type_id (int):
				Id of the raster types that are being processed

			is_categorical (bool):
				If True, the output of zonal_stats is dictionary with the unique raster values 
				as keys and pixel counts as values

			transform (string):
				Either of:
					- "area"
					- a string with placeholder e.g x * x to mean square of that value
			
			raster_resolution [Deprecated]:
				Resolution of the raster as explicity value if `raster` is set as a path to
				a raster file. If `raster` is set as a reference to a Raster model, the 
				resolution is retrieved from the raster metadata
		"""
		self.vector = vector
		self.rasters = rasters
		self.stats = ['mean']
		self.categorical = is_categorical
		self.raster_band_stats = [] #computed results per rasterband
		# self.raster_resolution = 30 # Resolution of the raster
		self.raster_type_id = raster_type_id # Raster type id
		self.value_placeholder = "x" #placeholder for value in transform equation
		self.transform = transform or self.value_placeholder # how to transform generated stats
		
		# if its categorical, we will just return the count per each category of values
		if is_categorical == True: 
			self.stats = []

	def get_stats(self):
		"""[summary]
		Because we are interested with the count of individual
		pixel values, we pass the categorical=True parameter
		to force the function to get us results as a dict 
		of the form {1.0: 1, 2.0: 9, 5.0: 40}

		As per the documentation:
		"You can treat rasters as categorical (i.e. raster values represent 
		discrete classes) if you’re only interested in the counts of unique pixel values."

		As per the documentation:
		"Using categorical, the output 
		is dictionary with the unique raster 
		values as keys and pixel counts as values:"

		Returns:
			List of stats for each rasterband.
			   
		"""
		# TODO: Retrieve the value of shapefile depending on what has been passed
		# TODO: Retrieve the value of raster and the mapping if necessary

		vectors = self.vector
		if self.is_vector_a_path():
			gdf = gpd.read_file(self.vector)
			vectors = gdf['geometry']

		stats_obj = {
			"mapping": self.get_raster_value_mapping(self.raster_type_id),
			'stats': []         
		}

		for raster in self.rasters: 
			results = []
			raster_path = get_absolute_media_path(raster.rasterfile.name)

			clipped_raster, ndata, rastfile = extract_pixels_using_vector(raster_path, vectors, categorical=True)

			# self.raster_band_stats = rasterstats.zonal_stats(vectors=vectors,
			# 				raster=raster_path,
			# 				categorical=self.categorical) #[1]
			self.raster_band_stats = rasterstats.zonal_stats(vectors=vectors,
							raster=rastfile,
							categorical=self.categorical) #[1]
			
			meta_data = self.get_raster_metadata(raster.id)

			mapping = meta_data['mapping']# self.get_raster_value_mapping(raster.id)
			resolution = meta_data['resolution']
			
			if self.categorical: 
				# we are only getting counts for each unique pixel value for categorical data            
				for layer_stats in self.raster_band_stats: # Loop through the results of each band
					for key in layer_stats.keys():
						if mapping:
							mp = [x for x in mapping if key==x['id']]
							if mp:
								val = layer_stats[key]
								results.append({ "key": key, 
										"label": str(mp[0]['label']),
										"raw_val": val,
										"value": self.transform_value(val, raster.id, resolution)
									})
						else:								
							val = layer_stats[key]
							results.append({ "key": key, 
									"label": str(key),
									"raw_val": val,
									"value": self.transform_value(val, raster.id, resolution)
								})
			else:
				results = self.raster_band_stats
			
			stats_obj['stats'].append({
				"raster_id": meta_data['raster'],
				"raster_name": raster.name,
				"resolution": meta_data['resolution'],
				'year': meta_data['year'],    
				'stats': results,
			})
		return stats_obj

	def append_metadata(self, results, raster_id):
		"""
		Append Raster metadata to the results

		Args:
			results:
				Results generated from the computations
		"""
		meta_data = self.get_raster_metadata(raster_id)
		return {
			"meta": {
				"raster": meta_data['raster'],
				"resolution": meta_data['resolution'],
				"mapping": meta_data['mapping'],                
			},
			"stats": [{
					'year': meta_data['year'],
					'values': results
				}] 
		}

	def transform_value(self, val, raster_id, raster_resolution=None):
		"""
		Transforms the raster band stat results.
		E.g you can calculate the area covered given the pixel count
		"""
		if self.transform == "area":
			resolution = raster_resolution or self.retrieve_raster_resolution(raster_id)
			return resolution * val
		else:
			return eval(self.transform.replace(self.value_placeholder, str(val)))
	
	def is_vector_a_path(self):
		"""
		Checks if the supplied `shapefile` parameter is a path to a file
		"""
		if self.vector.endswith(".shp"):
			return file_exists(self.vector, raise_exception=False)
		return False
 
	def get_raster_metadata(self, raster_id):
		"""
		Retrieves Raster metadata as stored in the database.

		Args:
			raster_id:
				ID of raster to retrieve metadata for

		Returns:
			Dictionary with the keys:
				`raster`: Name of the raster
				`resolution`: Resolution of the raster
				`mapping`: A dictionary of pixel value with the corresponding label
						E.g {1: "Forest", 2: "Grassland"}  
		"""
		model = Raster.objects.get(id=raster_id)
		mapping = [{"id": x.id, "val": x.value, "label": x.label, "color": x.color} for x in model.raster_type.rastervaluemapping_set.all()]

		meta = {
				"raster": model.id,
				"resolution": model.resolution or 1,
				"year": model.raster_year,
				"mapping": mapping,               
			}
		return meta

	def retrieve_raster_resolution(self, raster_id):
		"""
		Retrieve the resolution of a raster from its stored metadata in 
		the Raster model        
		"""
		meta = self.get_raster_metadata(raster_id)
		return meta['resolution']

	def get_raster_value_mapping(self, raster_type_id):
		"""
		Get a mapping of raster value with the corresponding label
		E.g {1: "Forest", 2: "Grassland"}

		Args:
			raster_type_id:
				Id of the raster type to retrieve metadata for
		"""
		model = RasterType.objects.get(id=raster_type_id)
		mapping = [{"id": x.id, "val": x.value, "label": x.label, "color": x.color} for x in model.rastervaluemapping_set.all()]
		return mapping

def get_band_number(band, raster_source):
	"""
	Determine the band number depending on the raster source (Landsat7, Landsat8, MODIS)
	Args:
		band (GenericRasterBandEnum): Band of the raster to be read. Valid RasterBandEnum value.
			  If image has single band, then pass band=GenericRasterBandEnum.LULC.	
		raster_source (RasterSourceEnum): Source of the raster. A valid value of RasterSourceEnum
	"""
	if raster_source == RasterSourceEnum.LULC:
		return 1
	
	band_map = {
		RasterSourceEnum.MODIS.value : { #modis
			GenericRasterBandEnum.RED.value: MODISBandEnum.RED.value,
			GenericRasterBandEnum.GREEN.value: MODISBandEnum.GREEN.value,
			GenericRasterBandEnum.BLUE.value: MODISBandEnum.BLUE.value,
			GenericRasterBandEnum.NIR.value: MODISBandEnum.NIR.value,
			GenericRasterBandEnum.SWIR1.value: MODISBandEnum.SWIR1.value,
		},
		RasterSourceEnum.LANDSAT7.value : { #landsat7
			GenericRasterBandEnum.RED.value: Landsat7BandEnum.RED.value,
			GenericRasterBandEnum.GREEN.value: Landsat7BandEnum.GREEN.value,
			GenericRasterBandEnum.BLUE.value: Landsat7BandEnum.BLUE.value,
			GenericRasterBandEnum.NIR.value: Landsat7BandEnum.NIR.value,
			GenericRasterBandEnum.SWIR1.value: Landsat7BandEnum.SWIR1.value,
		},
		RasterSourceEnum.LANDSAT8.value : { #landsat8
			GenericRasterBandEnum.RED.value: Landsat8BandEnum.RED.value,
			GenericRasterBandEnum.GREEN.value: Landsat8BandEnum.GREEN.value,
			GenericRasterBandEnum.BLUE.value: Landsat8BandEnum.BLUE.value,
			GenericRasterBandEnum.NIR.value: Landsat8BandEnum.NIR.value,
			GenericRasterBandEnum.SWIR1.value: Landsat8BandEnum.SWIR1.value,
		}
	}
	# return the band value depending on the source
	return band_map[raster_source.value][band.value]

def get_raster_values(raster_file, band, raster_source, windowed=False):
	"""Get raster values
	
	Args:
		raster_file (string): path of the raster file
		band (GenericRasterBandEnum): Band of the raster to be read. Valid GenericRasterBandEnum value.
			  If image has single band, then pass band=GenericRasterBandEnum.HAS_SINGLE_BAND.	
		raster_source (RasterSourceEnum): Source of the raster. A valid value of RasterSourceEnum		
		windowed (bool): Specifies if raster file is to be read in blocks. This 
			is needed for large files

	Returns:
		A numpy array	
	"""

	def get_file_path(raster_file):
		if file_exists(raster_file, raise_exception=False):
			return raster_file
		else:
			raster_file = get_media_dir() + raster_file
			if file_exists(raster_file, raise_exception=True):
				return raster_file
		return None

	if type(band) != GenericRasterBandEnum:
		raise AnalysisParamError(_("The band specified is invalid. Ensure the type is GenericRasterBandEnum"))
	if type(raster_source) != RasterSourceEnum:
		raise AnalysisParamError(_("The raster source specified is invalid. Ensure the type is RasterSourceEnum"))
	
	band_to_read = 1 # get_band_number(band=band, raster_source=raster_source)
	file = get_file_path(raster_file)
	if file:
		use_rasterio = True
		if not use_rasterio:        
			rst = GDALRaster(file, write=False)
			return rst.bands[band_to_read].data()
		else:
			if not windowed:
				dataset = rasterio.open(file)
				return dataset.read(1)
			else:				
				with rasterio.open(file) as src:
					"""	
					Well-bred files have identically blocked bands, 
					but GDAL allows otherwise and it's a good idea to test this assumption.
					The block_shapes property is a band-ordered list of block shapes and 
					set(src.block_shapes) gives you the set of unique shapes. Asserting that 
					there is only one item in the set is effectively the same as asserting 
					that all bands have the same block structure. If they do, you can use 
					the same windows for each.
					"""
					results_array = None
					assert len(set(src.block_shapes)) == 1
					for ji, window in src.block_windows(1):
						r = src.read(1, window=window)
						if ji == (0, 0): # first loop, initialize the numpy array
							results_array = np.array(r)
						else:
							results_array = np.append(results_array, r)
						# b, g, r = (src.read(k, window=window) for k in (1, 2, 3))
						# print((ji, r.shape, g.shape, b.shape))
						# break

					# for ji, window in src.block_windows(1):
					# 	b, g, r = (src.read(k, window=window) for k in (1, 2, 3))
					# 	print((ji, r.shape, g.shape, b.shape))
					# 	break
				return results_array
	return None

def get_raster_object(raster_file):
	"""Get Raster object metadata using the file
	"""
	if file_exists(raster_file, raise_exception=False):
		return GDALRaster(raster_file, write=False)
	else:
		raster_file = get_media_dir() + raster_file
		if file_exists(raster_file, raise_exception=True):
			return GDALRaster(raster_file, write=False)
	return None

# def save_raster(dataset, source_path, target_path, cols, rows, projection, geotransform):
# 	# geotransform = B5_2014.GetGeoTransform()
# 	# rasterSet = gdal.GetDriverByName('GisiTiff').Create(target_path, cols, rows, 1, gdal.GDT_Float32)
# 	# rasterSet.SetProjection(projection)
# 	# rasterSet.SetGeoTransform(geotransform)
# 	# rasterSet.GetRasterBand(1).WriteArray(dataset)
# 	# rasterSet.GetRasterBand(1).SetNoDataValue(-999)
# 	# rasterSet = None
# 	new_dataset = rasterio.open(target_path, 'w', driver='GTiff',
# 						height = rows, width = cols,
# 						count=1, dtype=dataset.dtype, #str(arr.dtype),
# 						crs='+proj=utm +zone=10 +ellps=GRS80 +datum=NAD83 +units=m +no_defs') #,
# 						# transform=geotransform)
# 	new_dataset.write(dataset, 1)
# 	new_dataset.close()

# 	raster = rasterio.open(source_path)
# 	profile = raster.meta

# 	array = ""
# 	with rasterio.open(rasterin) as src:
# 		meta = src.meta
# 		array = src.read(1)

# 	with rasterio.open(rasterout, 'w', **profile) as dst:
# 		dst.write(array.astype(rasterio.uint8), 1)

def get_raster_meta(rasterfile, set_default_nodata=True, default_nodata=settings.DEFAULT_NODATA):
	"""
	Get RasterFile metadata
	"""
	rasterin = get_absolute_media_path(rasterfile)
	with rasterio.open(rasterin) as src:
 		meta = src.meta

	if set_default_nodata:
		if 'nodata' not in src.meta or src.meta.get('nodata', None) == None:
			meta.update({'nodata': default_nodata})
		# if nodatavalue not within int range, set to default value
		nodataval = meta['nodata']
		if not (settings.MIN_INT <= nodataval <= settings.MAX_INT):
			meta.update({'nodata': default_nodata})

	return meta

def harmonize_raster_nodata(arry, file, ref_file):
	"""Read raster values while harmonizing the nodata values to ensure they are consistent

	Args:
		arry (array): Array whose nodata values we want to harmonize
		file (string): File path of the raster we want to read values from
		ref_file (string): File path of the raster whose nodata values we want to use 

	Returns:
		[array]: Array of harmonized values
	"""
	meta = get_raster_meta(get_absolute_media_path(file))
	nodata = meta.get('nodata')

	base_meta = get_raster_meta(get_absolute_media_path(ref_file))
	base_nodata = base_meta.get('nodata')
	values = np.where(arry == nodata, base_nodata, arry)
	return values

def save_raster(dataset, source_path, target_path, dtype=rasterio.int32, no_data=None):	
	"""
	Write raster dataset to disk

	Args:
		source_path (string): Path of raster where we will get the Metadata
		target_path (string): Path to save the raster
	"""
	rasterin = get_absolute_media_path(source_path.replace("//", "/"), use_static_dir=False)
	rasterout = target_path.replace("//", "/")
 
	# open source to extract meta
	meta = get_raster_meta(rasterin) 
	meta.update({
				 'dtype': dtype, # rasterio.uint8,
				 'compress': 'lzw',
				 'height': dataset.shape[0],
				 'width': dataset.shape[1],				 
				})	
	if no_data:
		meta.update({
			"nodata": no_data
		})
	with rasterio.open(rasterout, 'w', **meta) as dst:		
		# dst.write(dataset.astype(rasterio.uint8), 1)
		if len(dataset.shape) == 2:
			dst.write(dataset.astype(dtype), 1)
		else:
			dst.write(dataset.astype(dtype))
		
	"""
	bands = [x + 1 for x in list(range(rast.count))]
	rast.close()
	badbands = [7, 16, 25]

	nodatavalue = 255
	with rasterio.open(rasterout, 'w', **meta) as dst:
		with rasterio.open(rasterin) as src:
			for ID, b in enumerate(bands,1):
				# if b in ndvibands:
				# 	ndvi = src.read(b)
				# 	ndvi[ndvi != 0] = 0
				# 	dst.write(ndvi, ID)
				# else:
				data = src.read(b, masked=True)
				data = np.ma.filled(data, fill_value=nodatavalue)
				#data[data == 2] = 0
				dst.write(data, ID)
	dst.close
	"""
	return target_path.split("/")[-1]

def reproject_raster(reference_raster, raster, resampling=Resampling.average, set_default_nodata=True, default_nodata=settings.DEFAULT_NODATA):
	"""Checks if the CRS is the same, if not, reprojection is done.
	   Checks if extents are the same, if not clip or otherwise
	   Checks if resolution is the same, if not, resample

	Args:
		reference_raster (string): Reference raster to use as the base
		target_raster (string): Target raster that may need reprojection
		resampling (enum): One of the enumerated Rasterio Resampling methods

	Returns:
		(path, nodata): Tuple containing the path to the saved file and the value of nodata value
	"""
	ref_path = get_absolute_media_path(reference_raster)
	if reference_raster == raster: # if same file, do not reproject
		with rasterio.open(ref_path) as ref_file:
			ref_nodata = ref_file.meta.get('nodata') or default_nodata
		return raster, ref_nodata

	resampling = resampling or Resampling.nearest # default to Resampling.nearest
	
	dst_path = get_absolute_media_path(raster)
	trigger_reproject = False
	ref_nodata = None
	with rasterio.open(ref_path) as ref_file:
		ref_nodata = ref_file.meta.get('nodata') or default_nodata
		with rasterio.open(dst_path) as raster_src:
			src_affine, raster_affine = ref_file.meta['transform'], raster_src.meta['transform']
			src_resolution = [src_affine[0], -src_affine[4]]
			dst_resolution = [raster_affine[0], -raster_affine[4]]
		
			if ref_file.crs != raster_src.crs:
				# reproject
				trigger_reproject = True
				
			if ref_file.shape != raster_src.shape:
				# clip or otherwise	
				trigger_reproject = True

			if ref_file.transform != raster_src.transform: #transformation contains resolution
				# resample
				trigger_reproject = True
			
			if trigger_reproject:
				dst_crs = ref_file.crs
				transform, width, height = calculate_default_transform(
							ref_file.crs, dst_crs, ref_file.width, ref_file.height, *ref_file.bounds)
				kwargs = ref_file.meta.copy()
				kwargs.update({
					'crs': dst_crs,
					'transform': transform,
					'width': width,
					'height': height,
					'compress': 'lzw',
					'nodata': ref_nodata
				})

				dest_file = tempfile.NamedTemporaryFile(delete=False)
				with rasterio.open(dest_file.name, 'w', **kwargs) as new_raster:
					# for i in range(1, ref_file.count + 1): # Read all bands
					for i in range(1, 2): # read only the first band
						reproject(
							source=rasterio.band(raster_src, i),
							destination=rasterio.band(new_raster, i),
							src_transform=ref_file.transform,
							src_crs=ref_file.crs,
							dst_transform=transform,
							dst_crs=dst_crs,
							dst_nodata=ref_nodata,
							resampling=resampling)
				
				raster = dest_file.name

	return raster, ref_nodata

def return_raster_with_stats(request, datasource, prefix, change_enum, 
							   metadata_raster_path, nodata, resolution,
							   start_year, end_year, subdir=None, results=None,
							   extras={}):
	"""Generates a raster and computes the statistics

	Args:
		request (request): Http Request
		datasource (array): Raster array to save
		prefix (string): Name to prefix the generated raster with
		change_enum (enum.Enum): Type of Enumeration for different changes 
								e.g ProductivityChangeTernaryEnum, TrajectoryChangeTernaryEnum
		metadata_raster_path (string): Path of the raster where to get Metadata from
		nodata (int): Value of nodata
		resolution (int): Resolution to use to compute statistics
		subdir (string): Name of sub directory to save the raster
		results (object): An object already containing calculated values
		extras (dict): Extra key value object that you may want to return in addition to std values

	Returns:
		object : An object with url to download the generated raster and
					statistics categorized by the change_enum 
	"""
	# TODO validate change_enum
	# if type(change_enum) not in [StateChangeTernaryEnum, PerformanceChangeBinaryEnum, ProductivityChangeTernaryEnum]:
	# 	raise AnalysisParamError(_("The change enum source specified is invalid. Ensure it is a valid enumeration"))
	
	out_file = get_absolute_media_path(file_path=None, 
									is_random_file=True, 
									random_file_prefix=prefix,
									random_file_ext=".tif",
									sub_dir=subdir,
									use_static_dir=False)

	raster_file = save_raster(dataset=datasource, 
				source_path=metadata_raster_path,
				target_path=out_file)
	
	raster_url = "%s" % (get_download_url(request, raster_file, use_static_dir=False))
	results = results or []		
	
	# Get counts of change types		
	# unique, counts = np.unique(datasource[datasource != nodata], return_counts=True)			
	unique, counts = np.unique(datasource, return_counts=True)			
	val_counts = dict(zip(unique, counts)) # convert to {val:count} freq distribution dictionary
	
	if not results:
		for mapping in change_enum:
			key = cint(mapping.key)
			if key in val_counts:
				val = val_counts[mapping.key]
				results.append({
					'change_type': key,
					'label': str(mapping.label),
					'count': val,
					'area': val * (resolution or 1)
				})
			else:
				results.append({
					'change_type': key,
					'label': str(mapping.label),
					'count': 0,
					'area': 0
				})

	nodata_count = 0 
	if nodata in val_counts:
		nodata_count = val_counts[nodata]

	wms_url, layer = None, None
	if get_settings().enable_tiles:
		wms_url, layer = generate_tiles(raster_file=out_file, nodata=nodata, change_enum=change_enum)

	stats_obj = {
			# "baseline": "{}-{}".format(baseline_period[0], baseline_period[-1]),
			"base": start_year,
			"target": end_year,
			"rasterfile": raster_url,
			"nodataval": nodata,
			"nodata": nodata_count * (resolution or 1),
			'stats': results,
			'extras': extras,
			'tiles': {
				'url': wms_url,
				'layer': layer
			}
		} 
	return stats_obj      

def generate_tiles(raster_file, nodata, change_enum):
	"""Generate Tiles

	Args:
		raster_file (string): Raster file
		nodata (number): Nodata value
		change_enum (enum.Enum): Type of Enumeration for different changes 
								e.g ProductivityChangeTernaryEnum, TrajectoryChangeTernaryEnum
	Returns:
		Returns a WMS url
	"""
	geo = GeoServerHelper(analysis_enum=change_enum, nodata=nodata)
	return geo.upload_raster(raster_file) 

def test():	
	x = np.array([1, 2, 3])
	y =  np.array([4, 5, 6])
	nodata = 255
	add =  do_raster_operation([x, y], RasterOperationEnum.ADD, nodata)
	sub =  do_raster_operation([x, y], RasterOperationEnum.SUBTRACT, nodata)
	div =  do_raster_operation([x, y], RasterOperationEnum.DIVIDE, nodata)

def do_raster_operation(rasters, operation, nodata):
	"""Perform operations on rasters

	Args:
		rasters (list): List of rasters
		operation (RasterOperationEnum): Type of operation

	# TODO validate projection/extent/resolution
	"""
	res = None
	if isinstance(rasters, list):
		if operation == RasterOperationEnum.DIVIDE and len(rasters) != 2:
			raise AnalysisParamError(_("The list must contain only 2 arrays"))
		
		masked_rasters = []
		# Mask nodata values
		for i, itm in enumerate(rasters):
			# loop because np.ma.<arithmetic> replaces the masked values
			itm = ma.array(itm, fill_value=nodata)
			itm[itm==nodata] = ma.masked
			masked_rasters.append(itm)

			if i == 0:
				res = itm
			else:
				if operation == RasterOperationEnum.ADD:
					res = np.ma.add(res, itm)
				elif operation == RasterOperationEnum.SUBTRACT:
					res = np.ma.subtract(res, itm)
				elif operation == RasterOperationEnum.MULTIPLY:
					res = np.ma.multiply(res, itm)
				elif operation == RasterOperationEnum.DIVIDE:
					res = np.ma.divide(res, itm)
		
		# if operation == RasterOperationEnum.ADD:
		# 	res = np.add.reduce(masked_rasters)
		# elif operation == RasterOperationEnum.SUBTRACT:
		# 	res = np.subtract.reduce(masked_rasters)
		# elif operation == RasterOperationEnum.MULTIPLY:
		# 	res = np.multiply.reduce(masked_rasters)
		# elif operation == RasterOperationEnum.DIVIDE:
		# 	res = np.divide(masked_rasters[0], masked_rasters[1])
	
	return res

	# res = None
	# if isinstance(rasters, list):
	# 	if len(rasters) == 2: # operation on only multiple rasters	
	# 		rast1 = ma.array(rasters[0])			
	# 		rast1[rast1==nodata] = ma.masked
	# 		rast2 = ma.array(rasters[1])			
	# 		rast2[rast2==nodata] = ma.masked

	# 		if operation == RasterOperationEnum.ADD:
	# 			res = np.add(rast1, rast2)
	# 		elif operation == RasterOperationEnum.SUBTRACT:
	# 			res = np.subtract(rast1, rast2)
	# 		elif operation == RasterOperationEnum.DIVIDE:
	# 			res = np.divide(rast1, rast2)		
	# 	else:
	# 		raise AnalysisParamError(_("The list must contain only 2 arrays"))
	# return res

def resample_raster(raster_file, scale=2):
	"""
	Resample a raster file.

	Args:
		raster_file (string): Path to the raster file
	See https://gis.stackexchange.com/questions/368069/rasterio-window-on-resampling-open
	"""
	reference_file_path = get_absolute_media_path("LC_2007.tif")
	file_path_to_resample = get_absolute_media_path("LC_2008.tif")
	path_to_output = get_absolute_media_path("LC2007_2008get_raster_object.tif")
	# Open the datasets once
	# Load the reference profile
	with rasterio.open(reference_file_path) as src, rasterio.open(file_path_to_resample) as dst:
		profile = src.profile
		blocks = list(src.block_windows())
		height, width = src.shape
		result = np.full((height, width), dtype=profile['dtype'], fill_value=profile['nodata'])

		# Loop on blocks
		for _, window in blocks:
			row_offset = window.row_off + window.height
			col_offset = window.col_off + window.width

			# open image block
			src_values = src.read(
				1,
				masked=True,
				window=window
			)
			print (src_values)

			# Resample the window
			res_window = Window(window.col_off / scale, window.row_off / scale,
								window.width / scale, window.height / scale)

			try:
				dst_values = dst.read(
					out_shape=(
						src.count,
						int(window.height),
						int(window.width)
					),
					resampling=Resampling.average,
					masked=True,
					window=res_window
				)
			except:
				break

			print(dst_values.shape)

			# Do computations here e.g subtract the values
			result[window.row_off: row_offset, window.col_off: col_offset] = src_values + dst_values

	# Write result on disc
	with rasterio.open(path_to_output, 'w', **profile) as dataset:
		dataset.write_band(1, result)

	# path = get_absolute_media_path(raster_file)
	# with rasterio.open(path) as dataset:
	# 	# resample data to target shape
	# 	data = dataset.read(
	# 		out_shape=(
	# 			dataset.count,
	# 			int(dataset.height * scale),
	# 			int(dataset.width * scale)
	# 		),
	# 		resampling=Resampling.average
	# 	)

	# 	# scale image transform
	# 	transform = dataset.transform * dataset.transform.scale(
	# 		(dataset.width / data.shape[-1]),
	# 		(dataset.height / data.shape[-2])
	# 	)

def clip_raster_to_regional_vector(raster_file):
	"""
	Clip raster to only include values inside the regional vector
	"""
	regional_vector = RegionalAdminLevel.objects.all().first()
	if regional_vector:
		return clip_raster_to_vector(vector=json.loads(regional_vector.geom.geojson),
					raster_file=raster_file)		
	return raster_file

def clip_rasters(vector, models, ref_model=None, raise_file_missing_exception=True):
	"""Clip all rasters using the vector

	Args:
		vector (geojson): Polygon to be used for clipping
		models (List): Models whose raster files should be clipped
	
	Returns:
		tuple (nodata, list[raster, raster_file])
	"""
	res = []
	if not isinstance(models, list):
		models = [models]
	#meta = get_raster_meta(models[0].rasterfile.name)
	meta = get_raster_meta(ref_model.rasterfile.name) if ref_model else get_raster_meta(models[0].rasterfile.name)
	dest_nodata = meta['nodata']
	for i, model in enumerate(models):
		if model:
			if file_exists(get_absolute_media_path(model.rasterfile.name), raise_exception=raise_file_missing_exception):
				out_image, out_file, out_nodata = clip_raster_to_vector(model.rasterfile.name, 
												vector, use_temp_dir=True, 
												dest_nodata=dest_nodata)
				res.append([out_image, out_file])
			else:
				res.append([None, None])
		else:
			res.append([None, None])
	return (dest_nodata, res)

def mask_rasters(rasters, nodata):
	"""Clip all rasters using the vector

	Args:
		vector (geojson): Polygon to be used for clipping
		models (List): Models whose raster files should be clipped
	
	Returns:
		tuple (nodata, list[raster, raster_file])
	"""
	res = []
	if not isinstance(rasters, list):
		rasters = [rasters]
	for i, raster in enumerate(rasters):
		# is_masked = isinstance(rasters, ma.MaskedArray)
		arry = ma.array(raster)
		arry[arry==nodata] = ma.masked 
		res.append(arry)
	return res

def clip_raster_to_vector(raster_file, vector, use_temp_dir=True, dest_nodata=None):
	"""
	Mask out regions of a raster that are outside the polygons defined in the shapefile.

	Args:
		vector (geojson): Polygon to be used for clipping
		dest_nodata (number): Value to set as nodata when returning the clipped raster
	
	Returns (string, array): Tuple of Url of the clipped raster and the raster array
	"""
	file = get_absolute_media_path(raster_file)
	if not file_exists(file):
		return (None, None)
		
	all_touched = get_settings().raster_clipping_algorithm == "All Touched"
	# read the file and crop areas outside the polygon
	with rasterio.open(file) as src:
		nodata = dest_nodata if dest_nodata != None else src.meta['nodata'] or settings.DEFAULT_NODATA
		out_image, out_transform = rasterio.mask.mask(src, 
					[json.loads(vector)], # accepts array of shapes
					all_touched=all_touched,
					nodata=nodata,
					crop=True)
		out_meta = src.meta
	
	# update meta
	out_meta.update({"driver": "GTiff",
				"height": out_image.shape[1],
				"width": out_image.shape[2],
				"transform": out_transform
	})

	# enable compress
	out_meta.update({'compress': 'lzw'})

	# update nodata
	out_meta.update({'nodata': nodata})

	# get output file
	if use_temp_dir:
		out_file = get_temp_file(suffix=".tif")
	else:
		out_file = get_absolute_media_path(file_path=None, 
									is_random_file=True, 
									random_file_prefix="",
									random_file_ext=".tif")
									
	with rasterio.open(out_file, "w", **out_meta) as dest:
		dest.write(out_image)
	return (out_image, out_file, out_meta['nodata'])

def extract_pixels_using_vector(raster_file, vector, categorical=False, use_temp_dir=True):
	"""
	Extracts pixels covered by a vector
	Args:
		raster (string or array): Raster file or raster array
		vector (GeoJSON): GeoJSON string
		nodata: Value to use for nodata
		use_temp_dir: If True, the resulting raster will be stored in /tmp directory, else in the media directory
	Returns:
		tuple(array, nodata, file): Raster, value of nodata, filepath of the generated raster
	"""
	array, file, nodata = clip_raster_to_vector(raster_file, vector, use_temp_dir=use_temp_dir)
	return (array[0], nodata, file)
	"""
	if type(raster_file) == str:	
		file = get_absolute_media_path(raster_file)	
		if not file_exists(file):
			return (None, None)
	else:
		file = raster_file
	raster_stats = rasterstats.zonal_stats(vectors=vector,
						raster=file,
						categorical=categorical,
						all_touched=True,
						nodata=nodata,
						raster_out=True)
	return (raster_stats[0]['mini_raster_array'], raster_stats[0]['mini_raster_nodata']) 
	"""

	# bounds = json.loads(vector)['geometry']["bbox"]
	# if file_exists(file):
	# 	with rasterstats.io.Raster(raster=file, nodata=nodata) as raster_obj:
	# 		raster_subset = raster_obj.read(bounds=vector)
	# 		nodata = raster_obj.nodata
	# 	return (raster_subset, nodata)

def segment_and_concatenate(matrix, func=None, block_size=(16,16), overlap=(0,0)):
	"""Truncate matrix to a multiple of block_size. 
	Truncates the matrix to size that will be equally divisible by the block size
	
	See https://stackoverflow.com/questions/5073767/how-can-i-efficiently-process-a-numpy-array-in-blocks-similar-to-matlabs-blkpro
	
	Args:
		matrix (ndarray): Matrix that needs to be reduced
		func (function, optional): Function to be applied to the blocks (chunks). The function must return an ndarray. Defaults to None.
		block_size (tuple, optional): Size of chunks (blocks). Defaults to (16,16).
		overlap (tuple, optional): Are the chunks overlapping. Defaults to (0,0).

	Returns:
		ndarray: The reduced matrix
	"""
	if len(matrix.shape) > 2:
		matrix = matrix.reshape(-1, matrix.shape[2]) #reshape to remove first dimension

	matrix = matrix[:matrix.shape[0]-matrix.shape[0]%block_size[0], 
		  			:matrix.shape[1]-matrix.shape[1]%block_size[1]]
	rows = []
	for i in range(0, matrix.shape[0], block_size[0]):
		cols = []
		for j in range(0, matrix.shape[1], block_size[1]):
			max_ndx = (min(i+block_size[0], matrix.shape[0]),
					   min(j+block_size[1], matrix.shape[1]))
			res = func(matrix[i:max_ndx[0], j:max_ndx[1]])
			cols.append(res)
		rows.append(np.concatenate(cols, axis=1))
	return np.concatenate(rows, axis=0) # np.array([np.concatenate(rows, axis=0)]) # force return of a 3D matrix

from numpy.lib.stride_tricks import as_strided
def block_view(A, block= (3, 3)):
	"""Provide a 2D block view to 2D array. No error checking made.
	Therefore meaningful (as implemented) only for blocks strictly
	compatible with the shape of A."""
	# simple shape and strides computations may seem at first strange
	# unless one is able to recognize the 'tuple additions' involved ;-)
	shape= (A.shape[0]/ block[0], A.shape[1]/ block[1])+ block
	strides= (block[0]* A.strides[0], block[1]* A.strides[1])+ A.strides
	return as_strided(A, shape= shape, strides= strides)
	
def segmented_stride(M, fun, blk_size=(3,3), overlap=(0,0)):
	# This is some complex function of blk_size and M.shape
	stride = blk_size
	output = np.zeros(M.shape)

	B = block_view(M, block=blk_size)
	O = block_view(output, block=blk_size)

	for b,o in zip(B, O):
		o[:,:] = fun(b)

	return output

def view_process(M, fun=None, blk_size=(16,16), overlap=None):
	# truncate M to a multiple of blk_size
	from itertools import product
	output = np.zeros(M.shape)

	dz = np.asarray(blk_size)
	shape = M.shape - (np.mod(np.asarray(M.shape), 
						  blk_size))
	for indices in product(*[range(0, stop, step) 
						for stop,step in zip(shape, blk_size)]):
		# Don't overrun the end of the array.
		#max_ndx = np.min((np.asarray(indices) + dz, M.shape), axis=0)
		#slices = [slice(s, s + f, None) for s,f in zip(indices, dz)]
		output[indices[0]:indices[0]+dz[0], 
			   indices[1]:indices[1]+dz[1]][:,:] = fun(M[indices[0]:indices[0]+dz[0], 
			   indices[1]:indices[1]+dz[1]])

	return output
	
def clip_raster_to_vector_windowed(raster_file, vector, window_size, use_temp_dir=True, 
		apply_func=None, dest_nodata=None): 
	"""
	Mask out regions of a raster that are outside the polygons defined in the shapefile.

	Args:
		raster_file (string or array): Raster file or raster array
		vector (geojson): Polygon to be used for clipping
		window_size (tuple): How big are the blocks. A tuple of (width, height)
		use_temp_dir: If True, the resulting raster will be stored in /tmp directory, else in the media directory
		apply_func (function, optional): Function to applied to the windowed blocks. Defaults to None. 
										 This function must return an ndarray
		dest_nodata (number): Value to set as nodata when returning the clipped raster

	Returns:
		tuple(array, nodata, file): Raster, value of nodata, filepath of the generated raster
	"""
	def get_dest_file():
		# get output file
		if use_temp_dir:
			out_file = get_temp_file(suffix=".tif")
		else:
			out_file = get_absolute_media_path(file_path=None, 
										is_random_file=True, 
										random_file_prefix="",
										random_file_ext=".tif")
		return out_file
		
	# Clip the raster first
	array, file, nodata = clip_raster_to_vector(raster_file, vector, use_temp_dir=use_temp_dir, dest_nodata=dest_nodata)
	out_file = get_dest_file()# get output file
	out_raster = segment_and_concatenate(matrix=array, func=apply_func, block_size=window_size)
	res = save_raster(dataset=out_raster, source_path=file, target_path=out_file)
	return (out_raster, out_file, nodata)
	
def reshape_rasters(rasters):
	"""Returns an array whose size is smallest amongst the rasters
	Only reshapes rasters of shape (x, y) or (x, y, z)

	Args:
		rasters (list of nd-arrays): List of rasters to reshape
	"""
	is_masked = isinstance(rasters[0], ma.MaskedArray) if rasters else False
	# check if sizes are same
	if len(set([x.shape for x in rasters])) > 1:
		# check if shapes are similar in dimensions e.g (x, y, z) or (x,y)
		dimensions = set([len(x.shape) for x in rasters])
		if len(dimensions) > 1:
			raise AnalysisParamError("The specified inputs have different dimensions of %s", list(dimensions))
		
		if list(dimensions)[0] == 2: # If shape is (x, y)
			min_row_size = min([x.shape[0] for x in rasters])
			min_col_size = min([x.shape[1] for x in rasters])
			dest_rasters = []
			for rast in rasters:
				if not is_masked:
					dest_rasters.append(np.array(rast[:min_row_size, :min_col_size])) #extract min rows and cols
				else:
					dest_rasters.append(ma.array(rast[:min_row_size, :min_col_size])) #extract min rows and cols
		elif list(dimensions)[0] == 3: # If shape is (x, y, z)
			min_row_size = min([x.shape[1] for x in rasters])
			min_col_size = min([x.shape[2] for x in rasters])
			dest_rasters = []
			for rast in rasters:
				if not is_masked:
					dest_rasters.append(np.array(rast[:, :min_row_size, :min_col_size])) #extract min rows and cols
				else:
					dest_rasters.append(ma.array(rast[:, :min_row_size, :min_col_size])) #extract min rows and cols
		return dest_rasters
	return rasters

def reshape_raster(raster, shape):
	"""Returns an array whose size is of the shape speficied

	Args:
		raster (An nd-arrays): Raster to reshape
		shape (tuple(row, col)): Size of new raster
	"""
	# check if sizes are same
	if raster.shape != shape:
		dest_rast = raster[:shape[0] + 1, :shape[1] + 1]
		return dest_rast
	return raster

def get_raster_models(admin_zero_id=None, **args):
	"""Get Raster models from the database

	Returns:
		Enumerable: Retrun filtered Raster Models
	"""
	raster_models = Raster.objects.filter(**args)
	results = []
	if raster_models:
		# check if there are some associated with admin_0 id
		unique_years = list(set([x.raster_year for x in raster_models if x.raster_year]))
		for yr in list(set(unique_years)):
			year_models = [x for x in raster_models if x.raster_year==yr]
			regional_rasters = [x for x in year_models if not x.admin_zero]
			if admin_zero_id:
				# check if there is a country level one
				cntry_rasters = [x for x in year_models if x.admin_zero_id == admin_zero_id]
				if cntry_rasters:
					results.append(cntry_rasters[0])
				elif regional_rasters: #else add the first regional level raster
					results.append(regional_rasters[0])
			else:
				if regional_rasters:
					results.append(regional_rasters[0])
	
		# convert list to queryset
		return list_to_queryset(Raster, results)
	return raster_models #if no admin_zero_id

