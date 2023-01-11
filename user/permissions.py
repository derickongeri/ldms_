from rest_framework import permissions
from django.utils.translation import gettext as _

class IsSelf(permissions.BasePermission):
	"""
	Allow access only to current user
	"""
	message = _("Only the current logged in user has access")
	def has_object_permission(self, request, view, user):
		return bool(user == request.user)

class IsAdminOrSelf(permissions.BasePermission):
	"""
	Allow access only to admin users or the current user
	"""
	message = _("Only Admin users can access this object")
	def has_object_permission(self, request, view, user):
		is_self = bool(user == request.user)
		is_admin = (request.user.is_superuser or request.user.is_admin)
		return is_self or is_admin

class IsAdmin(permissions.BasePermission):
	"""
	Allow access only to admin users
	"""
	message = _("Only Admin users can access this object")
	def has_permission(self, request, view):
		return bool(request.user and (request.user.is_superuser or request.user.is_admin))

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an `owner` attribute.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Instance must have an attribute named `owner`.
        return obj.owner == request.user

class IsAnonymous(permissions.BasePermission):
	"""
	Allow access only to anonymous users
	"""
	def has_permission(self, request, view):
		return bool(request.user and not request.user.is_authenticated)
