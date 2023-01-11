# Import the library
from geo.Geoserver import Geoserver
import os
from ldms.utils.settings_util import get_settings
from django.conf import settings
from pysld.style import RasterStyle#, Style 
import re
import requests

class GeoServerHelper:
	def __init__(self, analysis_enum, nodata, workspace="ldms"): 
		# Initialize the library
		self.host = settings.GEOSERVER_HOST
		self.port = settings.GEOSERVER_PORT
		username = settings.GEOSERVER_USERNAME
		password = settings.GEOSERVER_PASSWORD
		self.site_url = "/geoserver"
		self.url = "{0}:{1}{2}".format(self.host, self.port, self.site_url)
		self.geo = Geoserver(service_url=self.url, username=username, password=password)
		self.workspace = workspace
		self.analysis_enum = analysis_enum		
		self.nodata = nodata
		self.sld = None
		self.style_name = re.search("'\w+'", str(analysis_enum)).group().strip("'")
		if workspace: 
			self.create_workspace(workspace)
		
	def get_style_xml(self):
		# def get_style(self, style_name, workspace: Optional[str] = None):
		"""
		Returns the style XML by style name.
		"""
		try:
			url = "{}/rest/styles/{}.sld".format(self.geo.service_url, self.style_name)
			if self.workspace is not None:
				url = "{}/rest/workspaces/{}/styles/{}.sld".format(
					self.geo.service_url, self.workspace, self.style_name
				)

			r = requests.get(url, auth=(self.geo.username, self.geo.password))
			return r.text# r.json()

		except Exception as e:
			return "get_style error: {}".format(e)

	def create_workspace(self, workspace):
		"""Create workspace

		Args:
			workspace (string): Workspace name
		"""
		exists = self.geo.get_workspace(workspace=workspace)
		if not exists or "Error " in exists:
			self.geo.create_workspace(workspace=workspace) 
		self.workspace = workspace

	def upload_raster(self, raster_path, workspace=None, layer_name=None):
		"""For uploading raster data to the geoserver

		Args:
			raster_path (string): Absolute raster file path e.g r'path\to\raster\file.tif'
			workspace (string, optional): Workspace name. Defaults to the workspace name specified at init
			layer_name (str, optional): Layer Name. Defaults to None.
		"""
		def parse_style_xml(xml):
			"""Replace the nodata place holder with actual nodata value
			"""
			return str(xml).replace(str(settings.NODATA_PLACEHOLDER), str(self.nodata))

		def preprocess_xml(xml):
			return xml.replace(" ", "").replace("\n", "").replace("\r", "")

		if not layer_name:
			layer_name = os.path.splitext(os.path.basename(raster_path))[0]
		self.geo.create_coveragestore(path=raster_path, 
					layer_name=layer_name, 
					workspace=workspace or self.workspace)
		# self.geo.create_coveragestyle(raster_path=raster_path, 
		# 							  style_name=layer_name, 
		# 							  number_of_classes=len(self.analysis_enum)
		# 							)		
		
		sld_xml = self.is_style_defined()
		if sld_xml:
			sld_xml = parse_style_xml(sld_xml)
				
		# Check if a previous sld has been uploaded 
		existing_style = self._retrieve_style()
		if not existing_style:
			sld_file = self.save_style_to_disk(sld_xml) if sld_xml else self._generate_style(raster_path)
			self.geo.upload_style(path=sld_file, name=self.style_name, workspace=self.workspace)
		elif existing_style and sld_xml: # if style is existing, check if published style is diff from the current one. If yes replace		
			# old_xml = self.get_style_xml()
			# if preprocess_xml(old_xml) != preprocess_xml(sld_xml):
			# 	sld_file = self.save_style_to_disk(sld_xml)
			# 	self.geo.upload_style(path=sld_file, name=self.style_name, workspace=self.workspace)			
			pass
		# associate layer with style
		self.geo.publish_style(layer_name=layer_name, style_name=self.style_name, workspace=self.workspace)
		# delete sld file from disk
		if not existing_style:			
			os.remove(sld_file)
		return self._generate_tile_url(raster_path)
	
	def _retrieve_style(self):
		"""
		Get already uploaded style that is associated with the change enum
		"""
		res = self.geo.get_style(self.style_name, self.workspace)
		if "get_style error" in res:
			return None
		return res

	def is_style_defined(self):
		"""
		Check if the SLD style is defined from Django admin PublishedComputation
		"""
		from ldms.utils.common_util import get_published_computation_by_change_enum
		obj = get_published_computation_by_change_enum(self.analysis_enum)
		if obj and obj.style:
			return obj.style
		return None

	def _generate_style(self, raster_path):
		"""
		Generate SLD file for the layer
		"""  
		enum_vals = [x.key for x in self.analysis_enum]
		sld = RasterStyle(style_name=self.style_name,
						number_of_class=len(enum_vals),
						continuous_legend=False)
		style = sld.coverage_style(max_value=max(enum_vals),
								   min_value=min(enum_vals))
		style = style.replace('type="intervals"', 'type="values"')								   
		self.sld = style.replace("</sld:ColorMap>", '<sld:ColorMapEntry color="#e95c47" label="Nodata" quantity="{0}" opacity="0"/>\n</sld:ColorMap>'.format(self.nodata))		
		
		# save sld file
		fl_name = self.save_style_to_disk(self.sld)
		# fl_name = "{0}.sld".format(self.style_name)
		# with open(fl_name, "w") as f:
		# 	f.write(self.sld)
		return fl_name

	def save_style_to_disk(self, style_xml):
		fl_name = "{0}.sld".format(self.style_name)
		with open(fl_name, "w") as f:
			f.write(style_xml)
		return fl_name

	def _generate_tile_url(self, raster_path):
		"""Generare WMS tile url

		Returns:
			string : Returns a tuple (url, layers) 
					e.g ('http://localhost:8600/geoserver/ldms/wms', 'ldms:modis_2000')'
		"""
		#setts = get_settings() 
		# url = "{0}:{1}/{2}/wms".format(os.getenv('GEOSERVER_HOST', setts.backend_url).rstrip('/'), 
		# 							   os.getenv("GEOSERVER_PORT", 8600),
		# 							   self.workspace)
		url = "{0}/{1}/wms".format(self.url, self.workspace)
		head, tail = os.path.split(raster_path)
		raster_name = tail.split(".")[0]
		layers = "{0}:{1}".format(self.workspace, raster_name)
		return (url, layers)

	def publish_style(self, layer_name, workspace=None):
		"""Publish raster file to server

		Args:
			layer_name ([type]): [description]
			workspace ([type], optional): [description]. Defaults to None.
		"""
		self.geo.publish_style(layer_name=layer_name, 
				style_name=self.style_name, 
				workspace=workspace or self.workspace)


	def delete_workspace(self, workspace=None):
		"""Delete workspace

		Args:
			workspace (string): Workspace name. Defaults to the workspace name specified at init
		"""
		 # delete workspace
		self.geo.delete_workspace(workspace=workspace or self.workspace)
		# delete workspace if `workspace` is set or `workspace` is same as `self.workspace`
		if not workspace or workspace == self.workspace:
			self.workspace = None

	def delete_layer(self, layer, workspace=None):
		"""Delete layer from workspace

		Args:
			layer (string): Layer name
			workspace (string): Workspace name. Defaults to the workspace name specified at init
		"""
		self.geo.delete_layer(layer_name=layer, workspace=workspace or self.workspace)


