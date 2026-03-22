from rest_framework.permissions import BasePermission
from .models import Membership

ROLE_HIERARCHY = {
    'founder': 4,
    'admin': 3,
    'moderator': 2,
    'member': 1,
}


class CommunityRolePermission(BasePermission):
    """
    Check user has the required role in the community identified by URL kwarg
    `community_slug`. Set `required_role` on the view (default: 'member').
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True  # staff can manage any community

        community_slug = view.kwargs.get('community_slug') or view.kwargs.get('slug')
        if not community_slug:
            return False

        required = getattr(view, 'required_role', 'member')
        required_level = ROLE_HIERARCHY.get(required, 1)

        try:
            membership = Membership.objects.get(
                user=request.user,
                community__slug=community_slug
            )
            return ROLE_HIERARCHY.get(membership.role, 0) >= required_level
        except Membership.DoesNotExist:
            return False
