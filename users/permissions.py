"""
Role-based permission classes and decorators for DeOrganized.

Groups:
  - production_staff  → can access /ops/ playout endpoints
  - platform_admin    → can access platform admin endpoints

Superusers bypass all group checks.
"""
from functools import wraps
from rest_framework.permissions import BasePermission
from django.http import JsonResponse


# -----------------------------------------------------------------------
# DRF Permission Classes (for class-based views / ViewSets)
# -----------------------------------------------------------------------

class IsProductionStaff(BasePermission):
    """Allow access to users in the 'production_staff' group or superusers."""
    message = 'Production staff access required.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return request.user.groups.filter(name='production_staff').exists()


class IsPlatformAdmin(BasePermission):
    """Allow access to users in the 'platform_admin' group or superusers."""
    message = 'Platform admin access required.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return request.user.groups.filter(name='platform_admin').exists()


class IsCreator(BasePermission):
    """Allow access to users with the 'creator' role."""
    message = 'Creator access required.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return getattr(request.user, 'role', None) == 'creator'


class HasPaidSubscription(BasePermission):
    """Allow access to users with a paid subscription (Starter, Pro, Enterprise)."""
    message = 'A paid subscription is required to access this feature.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        
        # Superusers and staff might bypass this depending on requirements
        # For now, only check specifically for the subscription object
        try:
            sub = request.user.subscription
            return sub.is_active and sub.plan != 'free'
        except Exception:
            # If no subscription object exists or other error
            return False


# -----------------------------------------------------------------------
# Function-based view decorators (for @api_view decorated views)
# -----------------------------------------------------------------------

def production_staff_required(view_func):
    """Decorator for function-based views — requires production_staff group."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if user.is_superuser or user.groups.filter(name='production_staff').exists():
            return view_func(request, *args, **kwargs)
        return JsonResponse(
            {'error': 'Production staff access required.'},
            status=403,
        )
    return _wrapped


def platform_admin_required(view_func):
    """Decorator for function-based views — requires platform_admin group."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if user.is_superuser or user.groups.filter(name='platform_admin').exists():
            return view_func(request, *args, **kwargs)
        return JsonResponse(
            {'error': 'Platform admin access required.'},
            status=403,
        )
    return _wrapped
