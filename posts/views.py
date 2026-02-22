from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django.db.models import Count, Exists, OuterRef, Subquery
from .models import Post
from .serializers import PostSerializer, PostCreateSerializer


class PostViewSet(viewsets.ModelViewSet):
    """
    ViewSet for community posts / feed.

    List (all): GET /api/posts/
    List (by author): GET /api/posts/?author=<id>
    Personalized feed: GET /api/posts/feed/
    Create: POST /api/posts/
    Update: PATCH /api/posts/{id}/
    Delete: DELETE /api/posts/{id}/
    """
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['-is_pinned', '-created_at']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PostCreateSerializer
        return PostSerializer

    def get_queryset(self):
        from users.models import Like
        from django.contrib.contenttypes.models import ContentType

        queryset = Post.objects.select_related('author')

        # Annotate with like/comment counts for performance
        queryset = queryset.annotate(
            _like_count=Count('likes', distinct=True),
            _comment_count=Count('comments', distinct=True),
        )

        # Annotate user_has_liked if authenticated
        if self.request.user.is_authenticated:
            post_ct = ContentType.objects.get_for_model(Post)
            queryset = queryset.annotate(
                _user_has_liked=Exists(
                    Like.objects.filter(
                        user=self.request.user,
                        content_type=post_ct,
                        object_id=OuterRef('pk')
                    )
                )
            )

        # Filter by author
        author_id = self.request.query_params.get('author')
        if author_id:
            queryset = queryset.filter(author_id=author_id)

        return queryset

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_permissions(self):
        if self.action in ['create']:
            return [IsAuthenticated()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return super().get_permissions()

    def update(self, request, *args, **kwargs):
        """Only allow author to edit their own post"""
        instance = self.get_object()
        if instance.author != request.user:
            return Response(
                {'error': 'You can only edit your own posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Only allow author (or staff) to delete"""
        instance = self.get_object()
        if instance.author != request.user and not request.user.is_staff:
            return Response(
                {'error': 'You can only delete your own posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def feed(self, request):
        """
        Personalized feed: posts from creators the user follows.
        GET /api/posts/feed/
        """
        from users.models import Follow

        # Get IDs of users this user follows
        following_ids = Follow.objects.filter(
            follower=request.user
        ).values_list('following_id', flat=True)

        queryset = self.get_queryset().filter(author_id__in=following_ids)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = PostSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = PostSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
