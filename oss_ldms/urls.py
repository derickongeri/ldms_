"""oss_ldms URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/dev/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf.urls import url, include
from django.urls import path
from ldms import views
from rest_framework.routers import DefaultRouter
from django.conf.urls.static import static
from django.conf import settings
from rest_framework.documentation import include_docs_urls
from ldms.analysis import analysis_router
from ldms.utils import auth_util
# from rest_framework_simplejwt import views as jwt_views

router = DefaultRouter()
# router.register(r'api/users', views.UserViewSet)
# router.register(r'api/groups', views.GroupViewSet)
# router.register(r'api/shapefiles', views.ShapeFileViewSet)
router.register(r'api/tasks', views.ScheduledTaskViewSet)
router.register(r'api/rasters', views.RasterViewSet)
router.register(r'api/vectregional', views.RegionalAdminLevelViewSet)
router.register(r'api/vect0', views.AdminLevelZeroViewSet)
router.register(r'api/vect1', views.AdminLevelOneViewSet)
router.register(r'api/vect2', views.AdminLevelTwoViewSet)
router.register(r'api/customvect', views.CustomShapeFileViewSet)
router.register(r'api/rastertype', views.RasterTypeViewSet)
router.register(r'api/settings', views.SystemSettingsViewSet)
router.register(r'api/gallery', views.GalleryViewSet)
router.register(r'api/faq', views.QuestionViewSet)
router.register(r'api/computationyears', views.PublishedComputationViewSet)

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^api-auth/', include('rest_framework.urls',
                                namespace='rest_framework')),
    url(r'^', include(router.urls)),
    url(r'tiles/', include('raster.urls')),
    url(r'^api/lulc/', analysis_router.enqueue_lulc, name='lulc'),    
    url(r'^api/soc/', analysis_router.enqueue_soc, name='soc'), 
    url(r'^api/forestchange/', analysis_router.enqueue_forest_change, name='forest_change'), 
    url(r'^api/forestfire/', analysis_router.enqueue_forest_fire, name='forest_fire'),    
    url(r'^api/state/', analysis_router.enqueue_state, name='state'),  
    url(r'^api/trajectory/', analysis_router.enqueue_trajectory, name='trajectory'),
    url(r'^api/performance/', analysis_router.enqueue_performance, name='performance'),   
    url(r'^api/productivity/', analysis_router.enqueue_productivity, name='productivity'),   
    url(r'^api/degradation/', analysis_router.enqueue_land_degradation, name='land_degradation'), 
    url(r'^api/aridity/', analysis_router.enqueue_aridity, name='aridity_index'), 
    url(r'^api/climatequality/', analysis_router.enqueue_climate_quality_index, name='climate_quality_index'),
    url(r'^api/soilquality/', analysis_router.enqueue_soil_quality_index, name='soil_quality_index'),  
    url(r'^api/managementquality/', analysis_router.enqueue_management_quality_index, name='management_quality_index'),  
    url(r'^api/vegetationquality/', analysis_router.enqueue_vegetation_quality_index, name='vegetation_quality_index'),  
    url(r'^api/esai/', analysis_router.enqueue_esai, name='esai'),  
    url(r'^api/carbonemission/', analysis_router.enqueue_forest_carbon_emission, name='carbonemission'), 
    url(r'^api/forestfirerisk/', analysis_router.enqueue_forest_fire_risk, name='forest_fire_risk'),  
    url(r'^api/ilswe/', analysis_router.enqueue_ilswe, name='ilswe'),  
    url(r'^api/rusle/', analysis_router.enqueue_rusle, name='rusle'), 
    url(r'^api/cvi/', analysis_router.enqueue_cvi, name='cvi'), 
    # url(r'^api/login/', auth_util.do_login, name="login"),
    # url(r'^api/register/', auth_util.create_user, name="register_user"),  
    # url(r'^api/updateuser/', auth_util.update_user, name="update_user"), 
    # url(r'^api/changepwd/', auth_util.change_password, name="change_password"),
    url(r'^api/uploadraster/', views.UploadRasterView.as_view(), name='upload-raster'),
    path('api/tasks/<int:task_id>/', analysis_router.task_result, name='task_result'),
    url(r'^api/test/', analysis_router.test_render, name='test'),    
    url(r'^api/iscached/', view=views.cache_exists, name='cache-exists'),
    url(r'^api/forest_fire_qml/', analysis_router.forest_fire_qml, name='forest_fire_qml'),  
    
    # Include the documentation for the API
    url(r'api-docs/', include_docs_urls(title='OSS LDMS API')),
    
    # Authentication
    # url('api/token/', jwt_views.TokenObtainPairView.as_view(), name='token_obtain_pair'),
    # url('api/token/refresh/', jwt_views.TokenRefreshView.as_view(), name='token_refresh'),

    # Custom user model urls
    path('api/', include('user.urls')),
]

# Allow serving of media files
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Allow serving of static files
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

urlpatterns += [
    path('django-rq/', include('django_rq.urls')),
]