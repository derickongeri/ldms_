import ee
from ee.ee_exception import EEException
import os
import logging

log = logging.getLogger(f'ldms.apps.{__name__}')

class GEEAccount:
	@property
	def service_account(self):
		return "osss-ldms@velvety-being-293814.iam.gserviceaccount.com"			
	
	@property
	def private_key(self):
		dir = os.path.dirname(__file__) or "."
		return os.path.join(dir, "private_key.json")

class GEE:
	"""Wrapper class for GEE integration
	https://github.com/google/earthengine-api/blob/master/python/examples/ipynb/Earth_Engine_REST_API_computation.ipynb
	"""
	def __init__(self, **kwargs):
		pass
   
	def initialize(self):
		"""
		Initialize and authenticate GEE
		"""
		self._authenticate()

	def _authenticate(self):
		"""
		Authenticate with service account if exists
		"""
		try:
			accnt = GEEAccount()
			credentials = ee.ServiceAccountCredentials(accnt.service_account, accnt.private_key)
			ee.Initialize(credentials)
			print(credentials)
		except EEException as e:
			print(str(e))
			log.log(logging.ERROR, str(e))