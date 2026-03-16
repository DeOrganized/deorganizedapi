from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from django.db.models import Count, F
from .models import News
from .serializers import (
    NewsSerializer, NewsListSerializer, NewsCreateUpdateSerializer
)
from api.permissions import IsOwnerOrReadOnly


class NewsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for News model.
    
    List: GET /api/news/
    Create: POST /api/news/ (authenticated users)
    Retrieve: GET /api/news/{id}/
    Update: PUT/PATCH /api/news/{id}/ (author only)
    Delete: DELETE /api/news/{id}/ (author only)
    
    Custom actions:
    - increment_view: POST /api/news/{id}/increment_view/
    - my_articles: GET /api/news/my_articles/
    """
    queryset = News.objects.select_related('author').annotate(
        _like_count=Count('likes', distinct=True),
        _comment_count=Count('comments', distinct=True)
    )
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'content', 'tags']
    ordering_fields = ['published_at', 'created_at', 'view_count', 'like_count']
    ordering = ['-published_at']
    lookup_field = 'slug'

    def get_object(self):
        """Support lookup by slug or numeric ID fallback"""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_value = self.kwargs.get(self.lookup_field) or self.kwargs.get('pk')
        
        if not lookup_value:
            from django.http import Http404
            raise Http404("No lookup value provided")

        from django.db.models import Q
        if str(lookup_value).isdigit():
            obj = queryset.filter(Q(slug=lookup_value) | Q(pk=int(lookup_value))).first()
        else:
            obj = queryset.filter(slug=lookup_value).first()
            
        if obj is None:
            from django.http import Http404
            raise Http404("Article not found")
            
        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer_class(self):
        if self.action == 'list':
            return NewsListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return NewsCreateUpdateSerializer
        return NewsSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by published status
        is_published = self.request.query_params.get('is_published')
        if is_published is not None:
            queryset = queryset.filter(is_published=is_published.lower() == 'true')
        elif not self.request.user.is_authenticated:
            # Anonymous users only see published articles
            queryset = queryset.filter(is_published=True)
        
        # Filter by category
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Filter by author
        author_id = self.request.query_params.get('author')
        if author_id:
            queryset = queryset.filter(author_id=author_id)
        
        # Filter by tags
        tags = self.request.query_params.get('tags')
        if tags:
            queryset = queryset.filter(tags__icontains=tags)
        
        return queryset
    
    def perform_create(self, serializer):
        """Set the author to the current user"""
        serializer.save(author=self.request.user)
    
    @action(detail=True, methods=['post'])
    def increment_view(self, request, pk=None):
        """Increment view count for an article"""
        article = self.get_object()
        article.view_count = F('view_count') + 1
        article.save(update_fields=['view_count'])
        article.refresh_from_db()
        return Response({'view_count': article.view_count})
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_articles(self, request):
        """Get current user's articles"""
        articles = self.get_queryset().filter(author=request.user)
        serializer = self.get_serializer(articles, many=True)
        return Response(serializer.data)
