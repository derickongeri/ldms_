import rasterio
import numpy as np
from ldms.utils.common_util import get_random_string
from ldms.utils.file_util import get_media_dir
from django.utils.translation import gettext as _

class VegetationIndex:
	"""
	Wrapper class for calculating different vegetation indicies
	"""	
	
	def __init__(self, red=None, green=None, nir=None, swir=None, **kwargs):
		
		self.red = red
		self.green = green
		self.nir = nir
		self.swir = swir
		if not red and not green and not nir and not swir:
			raise AnalysisParamError(_("No valid raster has been specified"))
		
		# allow division by zero
		np.seterr(divide='ignore', invalid='ignore')
		# set meta for the source file. validation will be done later
		self.meta = self.red.meta

		# we assume red will always be available
		if self.red and self.nir: # validate red and nir
			self.validate_bands(self.red, self.nir)
		if self.green: # validate green
			self.validate_bands(self.red, self.green)
		if self.swir: # validate swir
			self.validate_bands(self.red, self.swir)
		self.save_to_disk = kwargs.get('save_to_disk', False)
		
	def validate_bands(self, src_band, dst_band):
		"""
		Check resolution, size, src, and geotransformation are same.
		 In case these caracteristics do not coincide a warp, reproyection,
		 scale or any other geospatial process would be necessary.

		Args:
			src_band: Band to compare
			dst_band: Band to compare
		"""
		# compare projection
		prop = None
		if src_band.shape != dst_band.shape:
			prop = _("dimensions")
		if src_band.crs != dst_band.crs:
			prop = _("projections")
		if src_band.transform != dst_band.transform:
			prop = _("geotransforms")
		
		if prop:
			raise AnalysisParamError(_("The %s of the bands to must be the same in order to compute NDVI", (prop)))

	def ndvi(self):
		"""
		NDVI - normalized difference vegetation index 
		(nir - red)/(nir + red)
		"""
		self.validate_bands(self.red, self.nir)
		# allow division by zero
		np.seterr(divide='ignore', invalid='ignore')

		# calculate ndvi
		ndvi = (self.nir.astype(float) - self.red.astype(float)) / (self.nir + self.red)
		return self.return_results(filename="ndvi.tif", data=ndvi)

	def ndvi_change(self, r_src_band, nir_src_band, r_dst_band, nir_dst_band):
		"""
		Compute land cover change based on the differences
		in NDVI between the source and destination rasters
		Args:
			r_src_band (string): File path of RED band source raster
			nir_src_band (string): File path of NIR band source raster
			r_dst_band (string): File path of RED band target raster
			nir_dst_band (string): File path of NIR band target raster
		"""
		self.red = r_src_band
		self.nir = nir_src_band
		src_ndvi = self.ndvi()

		self.red = r_dst_band
		self.nir = nir_dst_band
		dst_ndvi = self.ndvi()
		
		ndvi_change = dst_ndvi - src_ndvi
		ndvi_change = np.where((src_ndvi>-999) & (dst_ndvi > -999), ndvi_change , -999)
		return self.return_results(filename="ndvichange", data=ndvi_change)

	def savi(self):
		"""
		SAVI - Soil Adjusted Vegetation Index
		(nir - red) * (1 + L)/(nir + red + L)
		"""
		data = (self.nir.astype(float) - self.red.astype(float) * (1 + 0.5)) / (self.nir + self.red + 0.5)
		return self.return_results(filename="savi.tif", data=data)

	def msavi(self):
		"""
		MSAVI - Modified Soil Adjusted Vegetation Index
		nir + 0.5 - (0.5 * sqrt((2 * nir + 1)^2 - 8 * (nir - (2 * red))))
		"""
		data = self.nir.astype(float) + 0.5 - (0.5 * np.sqrt((2 * self.nir.astype(float) + 1)**2 - 8 * (self.nir.astype(float) - (2 * self.red.astype(float)))))
		return self.return_results(filename="msavi.tif", data=data)

	def msavi2(self):
		"""
		SAVI - Modified Soil Adjusted Vegetation Index
		(2 * (nir + 1) - sqrt((2 * nir + 1)^2 - 8 * (nir - red)))/2
		"""
		data = (2 * (self.nir.astype(float) + 1) - np.sqrt((2 * self.nir.astype(float) + 1)**2 - 8 * (self.nir.astype(float) - self.red.astype(float))))/2
		return self.return_results(filename="msavi2.tif", data=data)

	def gemi(self):
		"""
		GEMI - Global Environmental Monitoring Index
		(((nir^2 - red^2) * 2 + (nir * 1.5) + (red * 0.5))/(nir + red + 0.5)) * (1 - ((((nir^2 - red^2) * 2 + (nir * 1.5) + (red * 0.5))/(nir + red + 0.5)) * 0.25)) - ((red - 0.125)/(1 - red))
		"""
		data = (((self.nir.astype(float)**2 - self.red.astype(float)**2) * 2 + (self.nir * 1.5) + (self.red * 0.5))/(self.nir + self.red + 0.5)) * (1 - ((((self.nir**2 - self.red**2) * 2 + (self.nir * 1.5) + (self.red * 0.5))/(self.nir + self.red + 0.5)) * 0.25)) - ((self.red - 0.125)/(1 - self.red))
		return self.return_results(filename="gemi.tif", data=data)

	def sr(self):
		"""
		SR - Simple Ratio Vegetation Index		
		nir/red
		"""
		data = (self.nir.astype(float) / self.red.astype(float))
		return self.return_results(filename="sr.tif", data=data)
	
	def tvi(self):
		"""
		TVI - Transformed Vegetation Index		
		sqrt((nir - red)/(nir + red) + 0.5)
		"""
		data = np.sqrt((self.nir.astype(float) - self.red.astype(float)) / (self.nir + self.red) + 0.5)
		return self.return_results(filename="sr.tif", data=data)
		
	def ttvi(self):
		"""
		TTVI - Thiam's Transformed Vegetation Index
		sqrt(abs((nir - red)/(nir + red) + 0.5))
		"""	
		data = np.sqrt(np.absolute((self.nir.astype(float) - self.red.astype(float)) / (self.nir + self.red) + 0.5))
		return self.return_results(filename="ttvi.tif", data=data)
	
	def ctvi(self):
		"""
		Corrected Transformed Vegetation Index
		(NDVI + 0.5)/sqrt(abs(NDVI + 0.5))
		"""
		ndvi = self.ndvi()
		data = (ndvi + 0.5) / np.sqrt(np.absolute(ndvi + 0.5))
		return self.return_results(filename="ctvi.tif", data=data)

	def dvi(self):
		"""
		Difference Vegetation Index
		s * nir - red
		"""
		s = self.nir.astype(float) / self.red.astype(float)
		data = s * self.nir.astype(float) - self.red.astype(float)
		return self.return_results(filename="dvi.tif", data=data)

	def wdvi(self):
		"""
		Weighted Difference Vegetation Index
		nir - s * red
		"""
		s = self.nir.astype(float) / self.red.astype(float)
		data = self.nir.astype(float) - s * self.red.astype(float)
		return self.return_results(filename="wdvi.tif", data=data)

	def gndvi(self):
		"""
		Green Normalised Difference Vegetation Index 
		(nir - green)/(nir + green)
		"""
		data = (self.nir.astype(float) - self.green.astype(float)) / (self.nir + self.green)
		return self.return_results(filename="gndvi.tif", data=data)
	
	def ndwi(self):
		"""
		Normalised Difference Water Index 
		(green - nir)/(green + nir)
		"""
		data = (self.green.astype(float) - self.nir.astype(float)) / (self.green + self.nir)
		return self.return_results(filename="ndwi.tif", data=data)

	def ndwi2(self):
		"""
		Normalised Difference Water Index 2
		(nir - swir2)/(nir + swir2)
		"""
		data = (self.nir.astype(float) - self.swir.astype(float)) / (self.nir + self.swir)
		return self.return_results(filename="ndwi2.tif", data=data)

	def mndwi(self):
		"""
		Modified Normalised Difference Water Index 
		(green - swir2)/(green + swir2)
		"""
		data = (self.green.astype(float) - self.swir.astype(float)) / (self.green + self.swir)
		return self.return_results(filename="mndwi.tif", data=data)

	def slavi(self):
		"""
		Specific Leaf Area Vegetation Index
		 nir/(red + swir2) 
		"""
		data = self.nir.astype(float) / (self.red.astype(float) + self.swir.astype(float))
		return self.return_results(filename="mndwi.tif", data=data)

	def rvi(self):
		"""
		RVI - Ratio Vegetation Index
		red / nir
		"""	
		data = (self.red.astype(float) / self.nir.astype(float))
		return self.return_results(filename="rvi.tif", data=data)

	def return_results(self, filename, data):
		"""Return computed results
		If save_to_disk parameter is specified, a path to output tiff file is returned, 
		otherwise the results array is returned
		Args:
			filename (string): Output file path
			data (array): Results of computation
		"""
		if self.save_to_disk:
			return self.write_to_disk(filename, data)
		return data

	def write_to_disk(self, filename, data):
		"""
		Save results as a tiff file

		Args:
			data (array): Computed results
			meta (dict): filename for the output file
		"""
		kwargs = self.meta.copy()
		# update kwargs and change datatype and set band as 1
		kwargs.update(
			dtype=rasterio.float32,
			count=1
		)
		outfile = self.get_file_path(filename)
		with rasterio.open(outfile, 'w', **kwargs) as dest:
			dest.write_band(1, data.astype(rasterio.float32))
		return outfile

	def get_file_path(self, filename):
		"""
		Generate random file name
		"""
		path = get_media_dir("/ndvi/")
		filename = get_random_string(length=12) + filename.split(".")[0] + "." + filename.split(".")[-1]
		return "%s%s" % (path, filename)
