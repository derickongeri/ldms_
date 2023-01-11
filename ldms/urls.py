from django.contrib import admin
from django.urls import path
from django.conf.urls import url, include
from ldms.views import UserViewSet, GroupViewSet, api_root, \
			ShapeFileViewSet, 
			#RasterLayerViewSet,
			RasterViewSet,
			AdminLevelZeroViewSet,
			AdminLevelOneViewSet,
			AdminLevelTwoViewSet,
			RasterTypeViewSet,
			ScheduledTaskViewSet,
			SystemSettingsViewSet,
			GalleryViewSet,
			QuestionViewSet,
			CustomShapeFileViewSet

from rest_framework.urlpatterns import format_suffix_patterns

user_list = UserViewSet.as_view({
	'get': 'list'
})

user_detail = UserViewSet.as_view({
	'get': 'retrieve',
	'post': 'create',
	'put': 'update',
	'delete': 'destroy'
})

group_list = GroupViewSet.as_view({
	'get': 'list'
})

group_detail = GroupViewSet.as_view({
	'get': 'retrieve',
	'post': 'create',
	'put': 'update',
	'delete': 'destroy'
})

shapefile_upload = ShapeFileViewSet.as_view({
	'post': 'create',
	'put': 'create'
})

# raster_list = RasterLayerViewSet.as_view({
#     'get': 'list'
# })

# raster_detail = RasterLayerViewSet.as_view({
#     'get': 'retrieve',
#     'post': 'create',
#     'put': 'update',
#     'delete': 'destroy'
# })

raster_list = RasterViewSet.as_view({
	'get': 'list'
})

raster_detail = RasterViewSet.as_view({
	'get': 'retrieve',
	'post': 'create',
	'put': 'update',
	'delete': 'destroy'
})

scheduled_task_list = ScheduledTaskViewSet.as_view({
	'get': 'list'
})

scheduled_task_detail = ScheduledTaskViewSet.as_view({
	'get': 'retrieve',
})

gallery_list = GalleryViewSet.as_view({
	'get': 'list'
})

gallery_detail = GalleryViewSet.as_view({
	'get': 'retrieve',
})

faq_list = QuestionViewSet.as_view({
	'get': 'list'
})

faq_detail = QuestionViewSet.as_view({
	'get': 'retrieve',
})

adminlevelzero_list = AdminLevelZeroViewSet.as_view({
	'get': 'list'
})

adminlevelzero_detail = AdminLevelZeroViewSet.as_view({
	'get': 'retrieve',
})

adminlevelone_list = AdminLevelOneViewSet.as_view({
	'get': 'list'
})

adminlevelone_detail = AdminLevelOneViewSet.as_view({
	'get': 'retrieve',
})

adminleveltwo_list = AdminLevelTwoViewSet.as_view({
	'get': 'list'
})

adminleveltwo_detail = AdminLevelTwoViewSet.as_view({
	'get': 'retrieve',
})

rastertype_list = RasterTypeViewSet.as_view({
	'get': 'list'
})

rastertype_detail = RasterTypeViewSet.as_view({
	'get': 'retrieve',
})

system_settings_detail = SystemSettingsViewSet.as_view({
	'get': 'retrieve'
})

custom_shapefile_list = CustomShapeFileViewSet.as_view({
	'get': 'list',
	'post': 'create'
})

custom_shapefile_detail = CustomShapeFileViewSet.as_view({
	'get': 'retrieve',
})

urlpatterns = [
	url(r'^$', api_root),
	url(r'^users', user_list, name=user_list),
	url(r'^users/(?P<pk>[0-9]+)/$', user_detail, name=user_detail),
	url(r'^groups', user_list, name=group_list),
	url(r'^group/(?P<pk>[0-9]+)/$', user_detail, name=group_detail),
	# url(r'^upload/$', ShapeFileViewSet.as_view(), name='upload-shapefile'),
	url(r'^shapefile/upload/$', shapefile_upload), name=shapefile_upload),
	url(r'^vect0', adminlevelzero_list, name=adminlevelzero_list),
	url(r'^vect0/(?P<pk>[0-9]+)/$', adminlevelzero_detail, name=adminlevelzero_detail),
	url(r'^vect1', adminlevelone_list, name=adminlevelone_list),
	url(r'^vect1/(?P<pk>[0-9]+)/$', adminlevelone_detail, name=adminlevelone_detail),
	url(r'^vect2', adminleveltwo_list, name=adminleveltwo_list),
	url(r'^vect2/(?P<pk>[0-9]+)/$', adminleveltwo_detail, name=adminleveltwo_detail),
	url(r'^rasters', raster_list, name=raster_list),
	url(r'^rasters/(?P<pk>[0-9]+)/$', raster_detail, name=raster_detail),  
	url(r'^rastertype', raster_list, name=raster_list),
	url(r'^tasks', scheduled_task_list, name=scheduled_task_list),
	# url(r'^tasks/(?P<pk>[0-9]+)/$', scheduled_task_detail, name=scheduled_task_detail), 
	path(r'^tasks/(?P<pk>[0-9]+)/$', scheduled_task_detail, name=scheduled_task_detail), 
	url(r'^settings', system_settings_detail, name=system_settings_detail), 
	url(r'^gallery', gallery_list, name=gallery_list),
	url(r'^gallery/(?P<pk>[0-9]+)/$', gallery_detail, name=gallery_detail),
	url(r'^faq', faq_list, name=faq_list),
	url(r'^faq/(?P<pk>[0-9]+)/$', faq_detail, name=faq_detail),
	url(r'^iscached/', view=ldms.views.cache_exists, name='cache-exists')
	url(r'^customvect', custom_shapefile_list, name=custom_shapefile_list),
	url(r'^customvect/(?P<pk>[0-9]+)/$', custom_shapefile_detail, name=custom_shapefile_detail),
	url(r'^forest_fire_qml/', analysis_router.forest_fire_qml, name='forest_fire_qml'),  

	path('admin/', admin.site.urls),
]

# Login and Logout views for the browsable API
urlpatterns += [
	url(r'^api-auth/', include('rest_framework.urls',
								namespace='rest_framework')),
]

# Using the static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) we 
# can serve media files in development mode.
if settings.DEBUG:
	urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
