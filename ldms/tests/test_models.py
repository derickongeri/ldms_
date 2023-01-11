from django.test import TestCase
from django.urls import include, path
from ldms.models import AdminLevelZero, AdminLevelOne, AdminLevelTwo
from rest_framework import status
from rest_framework.test import APITestCase, RequestsClient, URLPatternsTestCase
from ldms.utils.common import get_random_string, get_random_int
from django.contrib.gis.geos import GEOSGeometry
import json

class AdminLevelZeroTests(APITestCase):

    def create_instance(self, id):
        """
        Create a new instance of AdminLevelZero test instance
        """
        data = {    
            "gid_0": id,
            "name_0": get_random_string(10, 2),
            "cpu": "2",
            "geom": GEOSGeometry('MULTIPOLYGON((( 1 1, 1 2, 2 2, 1 1)))'),
        }
        return AdminLevelZero.objects.create(**data) 

    def test_listing(self):
        """
        Ensure the AdminLevelZero objects can be listed
        """
        url = ('http://0.0.0.0:8000/api/vect0/')
        id = get_random_int()
        admin = self.create_instance(id)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(AdminLevelZero.objects.count(), 1)
        self.assertEqual(AdminLevelZero.objects.get().gid_0, str(id))
        
        # check that the objects are serialized and returned
        objs = json.loads(response.content)
        self.assertEqual(objs[0].get('id'), admin.id)

        # check that geom and geometry field is excluded  because of GeoFeatureModelSerializer
        self.assertEqual('geom' in objs[0], False)
        self.assertEqual('geometry' in objs[0], False)

    def test_retrieve(self):
        """
        Test that retrieve works as expected
        """
        id = get_random_int()
        admin = self.create_instance(id)

        url = ('http://0.0.0.0:8000/api/vect0/' + str(admin.id) + "/")
        response = self.client.get(url, format='json')

        # check that the object is retrieved
        obj = json.loads(response.content)
        self.assertEqual(obj.get('id'), admin.id)

        # check that geometry field is included because of GeoFeatureModelSerializer
        self.assertEqual('geom' in obj, False)
        self.assertEqual('geometry' in obj, True)

class AdminLevelOneTests(APITestCase):

    def create_instance(self, id):
        """
        Create a new instance of AdminLevelOne test instance
        """
        parent = {
            "gid_0": id,
            "name_0": get_random_string(10, 2),
            "cpu": "2",
            "geom": GEOSGeometry('MULTIPOLYGON((( 1 1, 1 2, 2 2, 1 1)))'),
        }
        level_zero = AdminLevelZero.objects.create(**parent)
        data = {                
            'gid_0': level_zero.gid_0,
            'name_0': level_zero.name_0,
            'gid_1': id,	
            'name_1': get_random_string(10, 2),
            'geom': GEOSGeometry('MULTIPOLYGON((( 1 1, 1 2, 2 2, 1 1)))'),
        }
        return AdminLevelOne.objects.create(**data, admin_zero=level_zero) 

    def test_listing(self):
        """
        Ensure the AdminLevelOne objects can be listed
        """
        url = ('http://0.0.0.0:8000/api/vect1/')
        id = get_random_int()
        admin = self.create_instance(id)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(AdminLevelOne.objects.count(), 1)
        self.assertEqual(AdminLevelOne.objects.get().gid_0, str(id))

        # check that the objects are serialized and returned
        objs = json.loads(response.content)
        self.assertEqual(objs[0].get('id'), admin.id)

        # check that geom and geometry field is excluded  because of GeoFeatureModelSerializer
        self.assertEqual('geom' in objs[0], False)
        self.assertEqual('geometry' in objs[0], False)

    def test_listing_filtered(self):
        """
        Ensure the AdminLevelOne objects can be properly filtered
        """
        id1 = get_random_int()
        admin1 = self.create_instance(id1)

        id2 = get_random_int()
        admin2 = self.create_instance(id2)

        url = ('http://0.0.0.0:8000/api/vect1/?pid=' + str(admin1.admin_zero_id))
        response = self.client.get(url, format='json')

        queryset = AdminLevelOne.objects.filter(admin_zero_id=admin1.admin_zero_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(queryset.count(), 1) #check that only one item returned
        
        # check that the objects are filtered serialized and returned
        objs = json.loads(response.content)
        self.assertEqual(objs[0].get('id'), admin1.id)
        
        # check that geom and geometry field is excluded  because of GeoFeatureModelSerializer
        self.assertEqual('geom' in objs[0], False)
        self.assertEqual('geometry' in objs[0], False)

    def test_retrieve(self):
        """
        Test that retrieve works as expected
        """
        id = get_random_int()
        admin = self.create_instance(id)

        url = ('http://0.0.0.0:8000/api/vect1/' + str(admin.id) + "/")
        response = self.client.get(url, format='json')

        # check that the object is retrieved
        obj = json.loads(response.content)
        self.assertEqual(obj.get('id'), admin.id)

        # check that geometry field is included coz of GeoFeatureModelSerializer
        self.assertEqual('geom' in obj, False)
        self.assertEqual('geometry' in obj, True)

class AdminLevelTwoTests(APITestCase):
    
    def create_instance(self, id):
        """
        Create a new instance of AdminLevelTwo test instance
        """
        data = {
            "gid_0": id,
            "name_0": get_random_string(10, 2),
            "cpu": "2",
            "geom": GEOSGeometry('MULTIPOLYGON((( 1 1, 1 2, 2 2, 1 1)))'),
        }
        level_zero = AdminLevelZero.objects.create(**data)

        data = {                
            'gid_0': level_zero.gid_0,
            'name_0': level_zero.name_0,
            'gid_1': str(id),	
            'name_1': get_random_string(10, 2),
            'geom': GEOSGeometry('MULTIPOLYGON((( 1 1, 1 2, 2 2, 1 1)))'),
        }
        level_one = AdminLevelOne.objects.create(**data, admin_zero=level_zero) 

        data = {                
            'gid_0': level_zero.gid_0,
            'name_0': level_zero.name_0,
            'gid_1': level_one.gid_1,	
            'name_1': level_one.name_1,
            'gid_2': str(id),	
            'name_2': get_random_string(10, 2),
            'geom': GEOSGeometry('MULTIPOLYGON((( 1 1, 1 2, 2 2, 1 1)))'),
        }      
        return AdminLevelTwo.objects.create(**data, admin_one=level_one) 

    def test_listing(self):
        """
        Ensure the AdminLevelTwo objects can be listed
        """
        url = ('http://0.0.0.0:8000/api/vect2/')
        id = get_random_int()
        admin = self.create_instance(id)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(AdminLevelTwo.objects.count(), 1)
        self.assertEqual(AdminLevelTwo.objects.get().gid_0, str(id))
        
        # check that the objects are serialized and returned
        objs = json.loads(response.content)
        self.assertEqual(objs[0].get('id'), admin.id)

        # check that geom and geometry field is excluded  because of GeoFeatureModelSerializer
        self.assertEqual('geom' in objs[0], False)
        self.assertEqual('geometry' in objs[0], False)

    def test_listing_filtered(self):
        """
        Ensure the AdminLevelTwo objects can be properly filtered
        """
        id1 = get_random_int()
        admin1 = self.create_instance(id1)

        id2 = get_random_int()
        admin2 = self.create_instance(id2)

        url = ('http://0.0.0.0:8000/api/vect2/?pid=' + str(admin1.admin_one_id))
        response = self.client.get(url, format='json')

        queryset = AdminLevelOne.objects.filter(admin_zero_id=admin1.admin_one_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(queryset.count(), 1) #check that only one item returned
        
        # check that the objects are filtered serialized and returned
        objs = json.loads(response.content)
        self.assertEqual(objs[0].get('id'), admin1.id)

        # check that geom and geometry field is excluded  because of GeoFeatureModelSerializer
        self.assertEqual('geom' in objs[0], False)
        self.assertEqual('geometry' in objs[0], False)

    def test_retrieve(self):
        """
        Test that retrieve works as expected
        """
        id = get_random_int()
        admin = self.create_instance(id)

        url = ('http://0.0.0.0:8000/api/vect2/' + str(admin.id) + "/")
        response = self.client.get(url, format='json')

        # check that the object is retrieved
        obj = json.loads(response.content)
        self.assertEqual(obj.get('id'), admin.id)

        # check that geometry field is included coz of GeoFeatureModelSerializer
        self.assertEqual('geom' in obj, False)
        self.assertEqual('geometry' in obj, True)
