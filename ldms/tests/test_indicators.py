from django.test import TestCase
from django.urls import include, path
from ldms.models import AdminLevelZero, AdminLevelOne, AdminLevelTwo

from rest_framework.test import APITestCase, RequestsClient, URLPatternsTestCase
from ldms.utils.common_util import get_random_string, get_random_int
import numpy as np
import numpy.ma as ma
from ldms.analysis.productivity import Productivity
from django.conf import settings

import json

class ProductivityTest(TestCase):
	def setUp(self):
		# Setup run before every test method.
		pass
	
	def tearDown(self):
		# Clean up run after every test method.
		pass

	def test_performance_no_missing_data(self):
		"""
		Test computation of performance with no missing values
		"""
		ndvi_raster1 = np.array([
			[9 ,1],
			[4 ,500],
			[8 ,7]
		])
		ndvi_raster2 = np.array([
			[100 ,2],
			[8 ,7],
			[5 ,4]
		])
		
		rasters = [ndvi_raster1, ndvi_raster2]
		
		ecological_units = np.array([
			[2 ,3],
			[4 ,1],
			[2 ,4]
		])

		prod = Productivity()
		
		# check that frequency distributions of eco rasters are well coomputing
		unique_eco_units = prod.get_frequency_distribution(ecological_units)
		
		self.assertEquals(sorted(unique_eco_units.keys()), 
				sorted([1, 2, 3, 4])) # compare unique keys

		self.assertEquals(sorted(unique_eco_units.values()), 
				sorted([1, 1, 2, 2])) # compare count per values

		"""
		Percentile first element is the unique value of eco unit
		Second element is the 90th percentile for the values of mean ndvi
		located at the corresponding pixel occupied by the unique eco unit		
		"""
		perc_1 = np.percentile([253.5], 90) # 1 corresponding vals for eco unit 1
		perc_2 = np.percentile([54.5, 6.5], 90)# 6.3500000000000005 corresponding vals for eco unit 2
		perc_3 = np.percentile([1.5], 90)# 1.5 corresponding vals for eco unit 3
		perc_4 = np.percentile([6, 5.5], 90)# 5.95 corresponding vals for eco unit 4

		percentile_map = [ 
			[1, perc_1],
			[2, perc_2],
			[3, perc_3],
			[4, perc_4]
		]

		# Check that indicies of eco raster are picking well

		result = prod._compute_performance(rasters, ecological_units)
		
		# check that max ndvi computed well
		expected_max_ndvi_raster = np.array([
			[perc_2, perc_3],
			[perc_4, perc_1],
			[perc_2, perc_4]
		])
			
		self.assertEquals(True, np.array_equal(
				prod.max_ndvi_raster.data, 
				expected_max_ndvi_raster
			), "Max NDVI Rasters not matching"
		)
		
		# check means are computing well
		expected_mean = np.array([
					[54.5 , 1.5],
					[6. , 253.5 ],
					[6.5, 5.5]
				])	
		
		self.assertEquals(True, 
			np.array_equal(
				expected_mean, 
				prod.mean_ndvi.data
			), "Mean NDVI Rasters not matching"
		)

		# ratio = mean_ndvi / max_ndvi (90th percentile of mean_ndvi)
		expected_ratios = np.array([
			[54.5 / perc_2, 1.5 / perc_3],
			[6.0 / perc_4, 253.5 / perc_1],
			[6.5 / perc_2, 5.5 / perc_4]
		])

		self.assertEquals(True, np.array_equal(
				prod.ratios.data, 
				expected_ratios),
				"Ratios not matching"
		)

		# Expected mapping
		expected_mapping = np.array([
			[0, 0],
			[0, 0], 
			[2, 0]
		])

		self.assertEquals(True, np.array_equal(
				expected_mapping, 
				result),
				"Mapping not matching"
		)

	def test_performance_with_missing_data(self):
		"""
		Test computation of performance with missing values
		When any pixel value is missing, the corresponding values in other
		rasters will be masked
		"""
		ndvi_raster1 = np.array([
			[9 ,1],
			[4 ,500],
			[8 ,7]
		])
		ndvi_raster2 = np.array([
			[100, 2],
			[8, 7],
			[5, 4]
		])
		
		rasters = [ndvi_raster1, ndvi_raster2]
		
		ecological_units = np.array([
			[2, 3],
			[4, settings.DEFAULT_NODATA],
			[2, 4]
		])

		prod = Productivity()
		
		# check that frequency distributions of eco rasters are well coomputing
		unique_eco_units = prod.get_frequency_distribution(ecological_units)
		
		self.assertEquals(sorted(unique_eco_units.keys()), 
				sorted([2, 3, 4])) # compare unique keys

		self.assertEquals(sorted(unique_eco_units.values()), 
				sorted([1, 2, 2])) # compare count per values

		"""
		Percentile first element is the unique value of eco unit
		Second element is the 90th percentile for the values of mean ndvi
		located at the corresponding pixel occupied by the unique eco unit		
		"""
		perc_nodata = np.percentile([settings.DEFAULT_NODATA], 90) # 1 corresponding vals for eco unit 1
		# perc_1 = np.percentile([253.5], 90) # 1 corresponding vals for eco unit 1
		perc_2 = np.percentile([54.5, 6.5], 90)# 6.3500000000000005 corresponding vals for eco unit 2
		perc_3 = np.percentile([1.5], 90)# 1.5 corresponding vals for eco unit 3
		perc_4 = np.percentile([6, 5.5], 90)# 5.95 corresponding vals for eco unit 4

		percentile_map = [ 
			[1, perc_nodata],
			[2, perc_2],
			[3, perc_3],
			[4, perc_4]
		]

		# Check that indicies of eco raster are picking well

		result = prod._compute_performance(rasters, ecological_units)
		
		# check that max ndvi computed well
		expected_max_ndvi_raster = np.array([
			[perc_2, perc_3],
			[perc_4, ma.masked],
			[perc_2, perc_4]
		])
			
		self.assertEquals(True, np.array_equal(
				prod.max_ndvi_raster.data, 
				expected_max_ndvi_raster
			), "Max NDVI Rasters not matching"
		)
		
		# check means are computing well
		expected_mean = np.array([
					[54.5 , 1.5],
					[6. , 253.5 ],
					[6.5, 5.5]
				])	
		
		self.assertEquals(True, 
			np.array_equal(
				expected_mean, 
				prod.mean_ndvi.data
			), "Mean NDVI Rasters not matching"
		)

		# ratio = mean_ndvi / max_ndvi (90th percentile of mean_ndvi)
		expected_ratios = np.array([
			[54.5 / perc_2, 1.5 / perc_3],
			[6.0 / perc_4, ma.masked],
			[6.5 / perc_2, 5.5 / perc_4]
		])

		self.assertEquals(True, np.array_equal(
				prod.ratios.data, 
				expected_ratios),
				"Ratios not matching"
		)

		# Expected mapping
		expected_mapping = np.array([
			[0, 0],
			[0, settings.DEFAULT_NODATA], 
			[2, 0]
		])

		self.assertEquals(True, np.array_equal(
				expected_mapping, 
				result),
				"Mapping not matching"
		)