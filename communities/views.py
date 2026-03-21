from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from .models import Community, Membership, CommunityFollow
from .serializers import (
    CommunitySerializer, CommunityCreateSerializer,
    MembershipSerializer, MembershipWithCommunitySerializer,
)
from .permissions import CommunityRolePermission


class CommunityViewSet(viewsets.ModelViewSet):
    """
    list:     GET  /api/communities/
    create:   POST /api/communities/
    retrieve: GET  /api/communities/:slug/
    update:   PATCH /api/communities/:slug/      (admin+)
    destroy:  DELETE /api/communities/:slug/     (founder only)

    Custom actions:
    - my_communities: GET  /api/communities/my_communities/
    - feed:           GET  /api/communities/:slug/feed/
    - shows:          GET  /api/communities/:slug/shows/
    - events:         GET  /api/communities/:slug/events/
    - merch:          GET  /api/communities/:slug/merch/
    - follow:         POST /api/communities/:slug/follow/
    - followers:      GET  /api/communities/:slug/followers/
    """
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Community.objects.all()
        if self.action == 'list':
            qs = qs.annotate(member_count_annotated=Count('memberships', distinct=True))
        if self.action in ('retrieve', 'list'):
            qs = qs.prefetch_related(
                Prefetch(
                    'memberships',
                    queryset=Membership.objects.filter(role='founder').select_related('user'),
                    to_attr='founder_memberships'
                )
            )
        return qs

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return CommunityCreateSerializer
        return CommunitySerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        if self.action == 'create':
            return [IsAuthenticated()]
        if self.action in ('update', 'partial_update'):
            self.required_role = 'admin'
            return [IsAuthenticated(), CommunityRolePermission()]
        if self.action == 'destroy':
            self.required_role = 'founder'
            return [IsAuthenticated(), CommunityRolePermission()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        community = serializer.save(created_by=self.request.user)
        Membership.objects.create(
            user=self.request.user,
            community=community,
            role='founder'
        )

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_communities(self, request):
        """GET /api/communities/my_communities/ — user's communities with membership roles"""
        memberships = (
            Membership.objects
            .filter(user=request.user)
            .select_related('community')
            .prefetch_related(
                Prefetch(
                    'community__memberships',
                    queryset=Membership.objects.filter(role='founder').select_related('user'),
                    to_attr='founder_memberships'
                )
            )
        )
        serializer = MembershipWithCommunitySerializer(
            memberships, many=True, context={'request': request}
        )
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def feed(self, request, slug=None):
        """GET /api/communities/:slug/feed/ — community-scoped post feed"""
        from posts.models import Post
        from posts.serializers import PostSerializer
        from django.db.models import Count as DCount, Exists, OuterRef
        from users.models import Like
        from django.contrib.contenttypes.models import ContentType

        community = self.get_object()
        queryset = Post.objects.filter(community=community).select_related('author').annotate(
            _like_count=DCount('likes', distinct=True),
            _comment_count=DCount('comments', distinct=True),
        )
        if request.user.is_authenticated:
            post_ct = ContentType.objects.get_for_model(Post)
            queryset = queryset.annotate(
                _user_has_liked=Exists(
                    Like.objects.filter(
                        user=request.user,
                        content_type=post_ct,
                        object_id=OuterRef('pk')
                    )
                )
            )
        queryset = queryset.order_by('-created_at')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = PostSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = PostSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def shows(self, request, slug=None):
        """GET /api/communities/:slug/shows/ — community-scoped shows"""
        from shows.models import Show
        from shows.serializers import ShowListSerializer

        community = self.get_object()
        queryset = Show.objects.filter(
            community=community, status='published'
        ).select_related('creator')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ShowListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = ShowListSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def events(self, request, slug=None):
        """GET /api/communities/:slug/events/ — community-scoped events"""
        from events.models import Event
        from events.serializers import EventListSerializer

        community = self.get_object()
        queryset = Event.objects.filter(community=community).select_related('organizer')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = EventListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def merch(self, request, slug=None):
        """GET /api/communities/:slug/merch/ — community-scoped merch"""
        from merch.models import Merch
        from merch.serializers import MerchSerializer

        community = self.get_object()
        queryset = Merch.objects.filter(
            community=community, is_active=True
        ).select_related('creator')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = MerchSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = MerchSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def follow(self, request, slug=None):
        """POST /api/communities/:slug/follow/ — toggle follow"""
        community = self.get_object()
        follow, created = CommunityFollow.objects.get_or_create(
            user=request.user, community=community
        )
        if not created:
            follow.delete()
            return Response({'following': False})
        return Response({'following': True}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def followers(self, request, slug=None):
        """GET /api/communities/:slug/followers/"""
        from users.serializers import UserListSerializer

        community = self.get_object()
        users = [cf.user for cf in community.followers.select_related('user').all()]
        serializer = UserListSerializer(users, many=True, context={'request': request})
        return Response(serializer.data)


class MembershipViewSet(viewsets.ModelViewSet):
    """
    Nested under /api/communities/:community_slug/members/

    list:    GET    /api/communities/:slug/members/
    create:  POST   /api/communities/:slug/members/         (join)
    update:  PATCH  /api/communities/:slug/members/:id/     (change role, admin+)
    destroy: DELETE /api/communities/:slug/members/:id/     (leave self or remove, admin+)
    """
    serializer_class = MembershipSerializer

    def get_queryset(self):
        community_slug = self.kwargs.get('community_slug')
        return Membership.objects.filter(
            community__slug=community_slug
        ).select_related('user', 'community')

    def get_permissions(self):
        if self.action == 'list':
            return [AllowAny()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        community_slug = self.kwargs.get('community_slug')
        community = get_object_or_404(Community, slug=community_slug)
        serializer.save(user=self.request.user, community=community)

    def update(self, request, *args, **kwargs):
        """Change a member's role — requires admin+"""
        community_slug = self.kwargs.get('community_slug')
        try:
            requester = Membership.objects.get(
                user=request.user, community__slug=community_slug
            )
        except Membership.DoesNotExist:
            return Response({'error': 'Not a member'}, status=status.HTTP_403_FORBIDDEN)

        hierarchy = {'founder': 4, 'admin': 3, 'moderator': 2, 'member': 1}
        if hierarchy.get(requester.role, 0) < hierarchy['admin']:
            return Response({'error': 'Admin role required'}, status=status.HTTP_403_FORBIDDEN)

        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Leave community (self) or remove a member (admin+)"""
        community_slug = self.kwargs.get('community_slug')
        instance = self.get_object()

        if instance.user == request.user:
            if instance.role == 'founder':
                return Response(
                    {'error': 'Founders cannot leave. Transfer founder role first.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Removing someone else — requires admin+
        try:
            requester = Membership.objects.get(
                user=request.user, community__slug=community_slug
            )
        except Membership.DoesNotExist:
            return Response({'error': 'Not a member'}, status=status.HTTP_403_FORBIDDEN)

        hierarchy = {'founder': 4, 'admin': 3, 'moderator': 2, 'member': 1}
        if hierarchy.get(requester.role, 0) < hierarchy['admin']:
            return Response({'error': 'Admin role required'}, status=status.HTTP_403_FORBIDDEN)

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
