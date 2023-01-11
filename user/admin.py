from django.contrib import admin
from user.models import CustomUser, UserProfile
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from user.models import CustomUser
from user.forms import CustomUserCreationForm, CustomUserChangeForm

class UserProfileInline(admin.StackedInline):
	model = UserProfile
	extra = 1

class CustomUserAdmin(BaseUserAdmin):	
	"""The forms to add and change user instances.

	The fields to be used in displaying the User model.
	These override the definitions on the base UserAdmin
	"""
	fieldsets = (
		(None, {'fields': ('email', 'password')}),
		(_('Personal info'), {'fields': ('first_name', 'last_name')}),
		(_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_admin', 
									'is_superuser',	'groups', 'user_permissions')}),
		(_('Important dates'), {'fields': ('last_login', 'date_joined')}),
	)
	add_fieldsets = (
		(None, {
			'classes': ('wide',),
			'fields': ('email', 'password1', 'password2')}
		),
	)
	form = CustomUserChangeForm
	add_form = CustomUserCreationForm

	inlines = [UserProfileInline]
	list_display = ['email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_admin', 'is_superuser']
	list_filter = ['is_staff', 'is_superuser', 'is_admin',]
	search_fields = ('email', 'username', 'first_name', 'last_name')
	ordering = ('email',) 
	

admin.site.register(CustomUser, CustomUserAdmin)