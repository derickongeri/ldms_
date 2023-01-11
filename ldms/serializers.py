from rest_framework import serializers
from django.contrib.auth.models import User, Group
from .models import ShapeFile, Feature, AttributeValue
from .models import (AdminLevelZero, AdminLevelOne, AdminLevelTwo, 
        Raster, RasterType, RasterValueMapping, RegionalAdminLevel, ScheduledTask,
        SystemSettings, Gallery, Question, ComputationThreshold, CustomShapeFile,
        PublishedComputation, PublishedComputationYear)
from rest_framework_gis.serializers import GeoModelSerializer, GeoFeatureModelSerializer
from django.contrib.gis.gdal.field import OGRFieldTypes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404 
from raster.models import RasterLayer

import numpy as np
from django.conf import settings
from ldms.utils.file_util import read_image_tiff, get_media_dir
import json

# class UserSerializer(serializers.HyperlinkedModelSerializer):
#     institution = serializers.SerializerMethodField()
#     profession  = serializers.SerializerMethodField()
#     title = serializers.SerializerMethodField()
#     class Meta:
#         model = User
#         fields = ('username', 'id', 'email', 'first_name', 'last_name', 'is_active', 'institution', 'profession', 'title') # 'groups')

#     def get_user_profile(self, obj):
#         return UserProfile.objects.filter(user_id=obj.id).first()

#     def get_institution(self, obj):  
#         profile = self.get_user_profile(obj)      
#         return profile.institution if profile else ""

#     def get_profession(self, obj):        
#         profile = self.get_user_profile(obj)      
#         return profile.profession if profile else ""

#     def get_title(self, obj):  
#         profile = self.get_user_profile(obj)
#         return profile.title if profile else ""


# class GroupSerializer(serializers.HyperlinkedModelSerializer):
#     class Meta:
#         model = Group
#         fields = ('id', 'name')

class AttributeValueSerializer(serializers.ModelSerializer):
    """
    Serializer attribute values
    """
    attribute = serializers.SerializerMethodField()
    attribute_type = serializers.SerializerMethodField()
    # value = serializers.SerializerMethodField()
    class Meta:
        model = AttributeValue
        fields = ("value", "attribute", "attribute_type")

    def get_value(self, obj):
        """
        Transform values depending on the field type
        NB: Method must be prefixed with get_ 
        TODO: Handle Dates/Time/DateTime string types
        OGRFieldTypes = { 
                  0 : OFTInteger,
                  1 : OFTIntegerList,
                  2 : OFTReal,
                  3 : OFTRealList,
                  4 : OFTString,
                  5 : OFTStringList,
                  6 : OFTWideString,
                  7 : OFTWideStringList,
                  8 : OFTBinary,
                  9 : OFTDate,
                 10 : OFTTime,
                 11 : OFTDateTime,
            }
        """
        field_type = obj.attribute.type
        if field_type in [0]:
            return int(obj.value)
        if field_type in [2]:
            return float(obj.value)
        return obj.value

    def get_attribute(self, obj):
        """
        Method must be prefixed with get_        
        """
        return obj.attribute.name

    def get_attribute_type(self, obj):
        """
        Method must be prefixed with get_        
        """
        return obj.attribute.type

class FeatureSerializer(GeoFeatureModelSerializer):
    """
    Serializer shapefile features
    """
    feature_attributes = AttributeValueSerializer(many=True, source='attributevalue_set', read_only=True)

    class Meta:
        model = Feature
        geo_field = 'geom_geometrycollection'
        auto_bbox = True
        fields = ("id", "geom_geometrycollection", "feature_attributes", "feature_name") 

class ShapeFileSerializer(serializers.ModelSerializer):
    """
    Serialize Shapefile
    """
    features = FeatureSerializer(many=True, source='feature_set', read_only=True)
    # features = serializers.SerializerMethodField()
    
    class Meta:
        model = ShapeFile
        fields = ("id", "filename", "features")

    def __init__(self, *args, **kwargs):
        # First call the __init__ method of super class
        super(ShapeFileSerializer, self).__init__(*args, **kwargs)
        # self.fields.pop("features") #remove the features field

    # def __init__(self, *args, **kwargs):
    #     # First call the __init__ method of super class
    #     super(ShapeFileSerializer, self).__init__(*args, **kwargs)

    #     if 'context' in kwargs:
    #         if 'request' in kwargs['context']:
    #             tabs = kwargs['context']['request'].query_params.getlist('tab', [])
    #             if tabs:
    #                 included = set(tabs)
    #                 existing = set(self.fields.keys()) #get model fields

    #                 for other in existing - included:
    #                     self.fields.pop(other) #remove the fields that do not exist in the model

    def list(self, request):
        queryset = ShapeFile.objects.raw("""select id, filename from ldms_shapefile""")
        self.fields.pop("features") #remove the features field   
        serializer = ShapeFileSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        queryset = ShapeFile.objects.all()
        shapefile = get_object_or_404(queryset, pk=pk)
        serializer = ShapeFileSerializer(shapefile)
        return Response(serializer.data)

    def create(self, validated_data):
        queryset = ShapeFile.objects.all()
        return Task(id=None, **validated_data)

    def update(self, request, pk=None):
        queryset = ShapeFile.objects.all()
        shapefile = get_object_or_404(queryset, pk=pk)
        serializer = ShapeFileSerializer(shapefile)
        return Response(serializer.data)

    # def validate_filename(self, value):
    #     """
    #     Check that the filename is not empty
    #     """
    #     if not filename:
    #         raise serializers.ValidationError("The Shape File does not have a name")
    #     return value

    # def validate(self, data):
    #     """
    #     ! Alternatively perform additional validation here
    #     """
    #     if data['start'] > data['finish']:
    #         raise serializers.ValidationError("finish must occur after start")
    #     return data

class CustomShapeFileSerializer(serializers.ModelSerializer): #GeoFeatureModelSerializer):
    """
    Serializer custom shapefile
    """    
    class Meta:
        model = CustomShapeFile
        geo_field = 'geom'
        auto_bbox = True
        # fields = ("id", "owner", "geom", "shapefile_name", "shapefile")      
        # read_only_fields = ('id', 'geom')   
        fields = ("id", "owner", "shapefile_name",)         
        read_only_fields = ('id', )

class CustomShapeFileDetailSerializer(GeoFeatureModelSerializer):
    """
    Serializer custom shapefile
    """    
    class Meta:
        model = CustomShapeFile
        geo_field = 'geom'
        auto_bbox = True
        fields = ("id", "owner", "geom", "shapefile_name", "shapefile")         
        read_only_fields = ('id', 'geom')

class RegionalAdminLevelDetailSerializer(GeoFeatureModelSerializer):
    """
    Serializer to handle Admin Level Zero detailview
    """
    class Meta:
        model = RegionalAdminLevel
        geo_field = 'geom'
        auto_bbox = True
        fields = ("__all__")

class RegionalAdminLevelListSerializer(serializers.ModelSerializer):
    """
    Serializer to handle Regional Admin Level lists
    Excludes the Geometry data to improve load times
    """
    class Meta:
        model = RegionalAdminLevel
        fields = ['id', 'name']

class AdminLevelZeroDetailSerializer(GeoFeatureModelSerializer):
    """
    Serializer to handle Admin Level Zero detailview
    """
    class Meta:
        model = AdminLevelZero
        geo_field = 'geom'
        auto_bbox = True
        fields = ("__all__")

class AdminLevelZeroListSerializer(serializers.ModelSerializer):
    """
    Serializer to handle Admin Level Zero lists
    Excludes the Geometry data to improve load times
    """
    class Meta:
        model = AdminLevelZero
        fields = ['id', 'gid_0', 'name_0']

class AdminLevelOneDetailSerializer(GeoFeatureModelSerializer):
    """
    Serializer to handle Admin Level One detailview
    """
    class Meta:
        model = AdminLevelOne
        geo_field = 'geom'
        auto_bbox = True
        fields = ("__all__")

class AdminLevelOneListSerializer(serializers.ModelSerializer):
    """
    Serializer to handle Admin Level One lists
    Excludes the Geometry data to improve load times
    """
    class Meta:
        model = AdminLevelOne
        fields = ['id', 'admin_zero_id', 'name_1']

class AdminLevelTwoDetailSerializer(GeoFeatureModelSerializer):
    """
    Serializer to handle Admin Level Two detailview
    """
    class Meta:
        model = AdminLevelTwo
        geo_field = 'geom'
        auto_bbox = True
        fields = ("__all__")

class AdminLevelTwoListSerializer(serializers.ModelSerializer):
    """
    Serializer to handle Admin Level Two lists
    Excludes the Geometry data to improve load times
    """
    class Meta:
        model = AdminLevelTwo
        fields = ['id', 'admin_one_id', 'gid_2', 'name_2']

class RasterLayerListSerializer(serializers.ModelSerializer):
    """
    Serializer for RasterLayer listing
    """
    class Meta:
        model = RasterLayer
        fields = ("id", "name")

class RasterLayerDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for RasterLayer object
    """
    legend = serializers.SerializerMethodField()
    class Meta:
        model = RasterLayer
        fields = ("id", "name", "legend", "rasterfile")

    def get_legend(self, obj):
        """Get the unique values of the tiff image
        to facilitate creation of legend on the UI

        Args:
            obj ([type]): [description]
        """
        path = get_media_dir() + obj.rasterfile.name
        array = read_image_tiff(path, unique=True) 
        return array

class RasterListSerializer(serializers.ModelSerializer):
    """
    Serializer for Raster listing
    """
    class Meta:
        model = Raster
        fields = ("id", "name", "raster_year", "raster_type")

class RasterDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for Raster object
    """
    # legend = serializers.SerializerMethodField()
    class Meta:
        model = Raster
        # fields = ("id", "name", "legend", "rasterfile", "raster_year")
        fields = ("id", "name", "rasterfile", "raster_year")

    def get_legend(self, obj):
        """Get the unique values of the tiff image
        to facilitate creation of legend on the UI

        Args:
            obj ([type]): [description]
        """
        path = get_media_dir() + obj.rasterfile.name
        array = read_image_tiff(path, unique=True) 
        return array

class RasterValueMappingSerializer(serializers.ModelSerializer):
    """
    Serializer for Raster Value Mapping object
    """
    class Meta:
        model = RasterValueMapping
        fields = ("id", "value", "label", "color")

class RasterTypeDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for Raster Type object
    """
    # mapping = serializers.SerializerMethodField() 
    class Meta:
        model = RasterType
        fields = ("id", "name")

class RasterTypeListSerializer(serializers.ModelSerializer):
    """
    Serializer for Raster Type object
    """
    class Meta:
        model = RasterType
        fields = ("id", "name")

class ScheduledTaskListSerializer(serializers.ModelSerializer):
    """
    Serializer for ScheduledTask listing
    """
    class Meta:
        model = ScheduledTask
        fields = ("id", "name", "status")

class ScheduledTaskDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for ScheduledTask object
    """    
    args = serializers.SerializerMethodField()
    result = serializers.SerializerMethodField()
    class Meta:
        model = ScheduledTask
        fields = ("id", "name", "result", "error", "status", "method", "args")

    def get_args(self, obj):
        """
        Method must be prefixed with get_        
        """
        if obj.args:
            return json.loads(obj.args)
        return "{}"

    def get_result(self, obj):
        """
        Method must be prefixed with get_        
        """
        if obj.result:
            return json.loads(obj.result)
        return "{}"

class ComputationThresholdSerializer(serializers.ModelSerializer):
    """
    Serializer for ComputationThresholds
    """
    class Meta:
        model = ComputationThreshold
        fields = "__all__"

class SystemSettingsDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for SystemSettings object
    """    
    email_host_password = serializers.SerializerMethodField()
    thresholds = serializers.SerializerMethodField()

    class Meta:
        model = SystemSettings
        fields = "__all__"

    def get_email_host_password(self, obj):
        """
        Method must be prefixed with get_        
        """
        return obj.email_host_password # ""
    
    def get_thresholds(self, object):
        """
        Get size limit thresholds
        """
        serializer = ComputationThresholdSerializer(ComputationThreshold.objects.all(), many=True)    
        return serializer.data# objs

class GalleryListSerializer(serializers.ModelSerializer):
    """
    Serializer for Gallery listing
    """
    class Meta:
        model = Gallery
        fields = ("image_name", "image_file", "is_published", "image_desc")

class GalleryDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for Gallery object
    """        
    class Meta:
        model = Gallery
        fields = ("image_name", "image_file", "is_published", "image_desc")


class QuestionListSerializer(serializers.ModelSerializer):
    """
    Serializer for Question listing
    """
    topic = serializers.SerializerMethodField()
    class Meta:
        model = Question
        fields = ("question_text", "answer", "topic")

    def get_topic(self, obj):
        return obj.topic.topic_name if obj.topic else ""

class QuestionDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for Question object
    """     
    topic = serializers.SerializerMethodField()   
    class Meta:
        model = Question
        fields = ("question_text", "answer", "topic")

    def get_topic(self, obj):
        return obj.topic.topic_name if obj.topic else ""

class PublishedComputationListSerializer(serializers.ModelSerializer):
    """
    Serializer for Question listing
    """
    published_years = serializers.SerializerMethodField()
    class Meta:
        model = PublishedComputation
        fields = ("computation_type", "admin_zero", "published_years")

    def get_published_years(self, obj):
        return sorted(PublishedComputationYear.objects.filter(published_computation_id=obj.id).values_list("published_year", flat=True))