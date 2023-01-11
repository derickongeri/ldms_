from django.contrib import admin
from ldms.models import ShapeFile, Feature, Attribute, AttributeValue, ScheduledTask
from ldms.models import (AdminLevelZero, AdminLevelOne, AdminLevelTwo,
					Raster, RasterType, RasterValueMapping,
					RegionalAdminLevel, SystemSettings,
					Gallery, Topic, Question, ComputationThreshold,
					CustomShapeFile, PublishedComputation, PublishedComputationYear,
					DataImportSettings)
from ldms.forms import SystemSettingsForm

from raster.models import (LegendSemantics,
				RasterLayer,
				RasterTile,
				RasterLayerMetadata,
				LegendEntry,
				Legend)

# Register your models here.
class FeatureInline(admin.StackedInline):
	model = Feature
	extra = 1

class ShapeFileAdmin(admin.ModelAdmin):
	fieldsets = [
		(None, {'fields': ['filename', 'geom_type']}),
	]
	inlines = [FeatureInline]
	list_display = ['filename', 'geom_type']
	list_filter = ['filename']
	search_fields = ['filename']

class AdminLevelZeroAdmin(admin.ModelAdmin):
	list_display = ['gid_0', 'name_0']

class AdminLevelOneAdmin(admin.ModelAdmin):
	list_display = ['name_0', 'name_1', 'varname_1']
	list_filter = ['admin_zero']

class AdminLevelTwoAdmin(admin.ModelAdmin):
	list_display = ['name_0', 'name_1', 'name_2', 'type_2']
	list_filter = [ 'name_0', 'admin_one']

class RasterAdmin(admin.ModelAdmin):
	list_display = ["name", "rasterfile", "raster_category", "raster_year", "raster_source", "admin_zero"]
	list_filter = ["raster_category", "admin_zero", "raster_source", 'raster_year']

	# def change_view(self, request, object_id, extra_context=None):
	# 	self.exclude = ('raster_type', ) #exclude raster type
	# 	return super().change_view(request, object_id, extra_context)

	def get_fields(self, request, obj=None):
		fields = super().get_fields(request, obj)
		# if obj:
		# fields.remove('raster_type')#exclude raster type
		return fields

class RegionalAdminLevelAdmin(admin.ModelAdmin):
	list_display = ["id", "name"]

class RasterValueMappingInline(admin.TabularInline):
    model = RasterValueMapping
    extra = 1

class ScheduledTaskAdmin(admin.ModelAdmin):
	list_display = ['name', 'created_on', 'status', 'succeeded']
	list_filter = ['succeeded']

class RasterTypeAdmin(admin.ModelAdmin):
	inlines = [RasterValueMappingInline]

class SystemSettingsAdmin(admin.ModelAdmin):
	form = SystemSettingsForm

	list_display = ['email_host', 'email_host_user', 'email_host_protocol', 'email_host_port', "task_results_url"]

class GalleryAdmin(admin.ModelAdmin):
	list_display = ['image_name', 'image_file', 'is_published']

class TopicAdmin(admin.ModelAdmin):
	list_display = ("topic_name", "slug", "sort_order")

class QuestionAdmin(admin.ModelAdmin):
	list_display = ("question_text", "topic", "answer", "status", "protected", "sort_order")

class ComputationThresholdAdmin(admin.ModelAdmin):
	list_display = ("datasource", "guest_user_threshold", "authenticated_user_threshold", "enable_guest_user_limit", "enable_signedup_user_limit")

class CustomShapeFileAdmin(admin.ModelAdmin):
	list_display = ("shapefile_name", "owner", "shapefile")

class PublishedComputationYearInline(admin.TabularInline):
	model = PublishedComputationYear
	extra = 1

class PublishedComputationAdmin(admin.ModelAdmin):
	fieldsets = [
		(None, {'fields': ['computation_type', 'style', 'admin_zero', 'published']}),
	]
	inlines = [PublishedComputationYearInline]
	list_display = ['computation_type', 'published', 'admin_zero']
	list_filter = ['computation_type']
	search_fields = ['computation_type']


class DataImportSettingsAdmin(admin.ModelAdmin):
	list_display = ['raster_data_file']


# admin.site.register(ShapeFile, ShapeFileAdmin)
# admin.site.register(Feature)
# admin.site.register(Attribute)
# admin.site.register(AttributeValue)
admin.site.register(AdminLevelZero, AdminLevelZeroAdmin)
admin.site.register(AdminLevelOne, AdminLevelOneAdmin)
admin.site.register(AdminLevelTwo, AdminLevelTwoAdmin)
admin.site.register(Raster, RasterAdmin)
# admin.site.register(RasterType, RasterTypeAdmin)
admin.site.register(RegionalAdminLevel, RegionalAdminLevelAdmin)
admin.site.register(ScheduledTask, ScheduledTaskAdmin)
admin.site.register(SystemSettings, SystemSettingsAdmin)
admin.site.register(Gallery, GalleryAdmin)
admin.site.register(Topic, TopicAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(ComputationThreshold, ComputationThresholdAdmin)
admin.site.register(CustomShapeFile, CustomShapeFileAdmin)
admin.site.register(PublishedComputation, PublishedComputationAdmin)
admin.site.register(DataImportSettings, DataImportSettingsAdmin)

admin.site.unregister(LegendSemantics)
admin.site.unregister(RasterLayer)
admin.site.unregister(RasterTile)
admin.site.unregister(RasterLayerMetadata)
admin.site.unregister(LegendEntry)
admin.site.unregister(Legend)