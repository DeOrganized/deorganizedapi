from rest_framework.exceptions import PermissionDenied
from .models import Membership

ROLE_HIERARCHY = {
    'founder': 4,
    'admin': 3,
    'moderator': 2,
    'member': 1,
}


class CommunityWriteMixin:
    """
    For existing viewsets (Post, Show, Event, Merch) where community context
    arrives as a request body field rather than a URL kwarg.

    Checks membership and minimum role on create/update when `community` is
    provided. If no community is provided the action is allowed as-is for
    backward compatibility.

    Usage:
        class PostViewSet(CommunityWriteMixin, viewsets.ModelViewSet):
            community_write_role = 'member'

    CommunityWriteMixin MUST appear before ModelViewSet in MRO.
    """
    community_write_role = 'member'

    def check_community_permission(self, request, min_role=None):
        min_role = min_role or self.community_write_role
        community_id = request.data.get('community')

        if not community_id:
            return  # no community scope — backward compat, allow

        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")

        try:
            membership = Membership.objects.get(
                user=request.user,
                community_id=community_id
            )
            required_level = ROLE_HIERARCHY.get(min_role, 1)
            user_level = ROLE_HIERARCHY.get(membership.role, 0)
            if user_level < required_level:
                raise PermissionDenied(f"Requires {min_role} role in this community")
        except Membership.DoesNotExist:
            raise PermissionDenied("Not a member of this community")

    def perform_create(self, serializer):
        self.check_community_permission(self.request)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self.check_community_permission(self.request)
        super().perform_update(serializer)
