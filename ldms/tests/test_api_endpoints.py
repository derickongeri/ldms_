from django.test import TestCase
from django.urls import include, path
from ldms.models import AdminLevelZero, AdminLevelOne, AdminLevelTwo
from rest_framework import status
from rest_framework.test import APITestCase, RequestsClient, URLPatternsTestCase

class LulcAPITest(TestCase):
	def setUp(self):
		# Setup run before every test method.
		pass
	
	def tearDown(self):
		# Clean up run after every test method.
		pass

    def test_authenticated(self):
        pass

    def test_unauthenticated(self):
        pass

    