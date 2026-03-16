from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from django.db.models import Count, Q
from django.utils import timezone
from .models import Event
from .serializers import (
    EventSerializer, EventListSerializer, EventCreateUpdateSerializer
)
from api.permissions import IsOwnerOrReadOnly


class EventViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Event model.
    
    List: GET /api/events/
    Create: POST /api/events/ (authenticated users)
    Retrieve: GET /api/events/{id}/
    Update: PUT/PATCH /api/events/{id}/ (organizer only)
    Delete: DELETE /api/events/{id}/ (organizer only)
    
    Custom actions:
    - upcoming: GET /api/events/upcoming/
    - past: GET /api/events/past/
    - my_events: GET /api/events/my_events/
    """
    queryset = Event.objects.select_related('organizer').annotate(
        _like_count=Count('likes', distinct=True),
        _comment_count=Count('comments', distinct=True)
    )
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'venue_name']
    ordering_fields = ['start_datetime', 'created_at', 'like_count']
    ordering = ['start_datetime']
    
    def get_object(self):
        """Support lookup by slug or numeric ID"""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_value = self.kwargs.get('pk', '')
        
        # Try slug lookup first, then fall back to numeric ID
        if lookup_value.isdigit():
            from django.db.models import Q
            obj = queryset.filter(Q(slug=lookup_value) | Q(pk=int(lookup_value))).first()
        else:
            obj = queryset.filter(slug=lookup_value).first()
        
        if obj is None:
            from django.http import Http404
            raise Http404("Event not found")
        
        self.check_object_permissions(self.request, obj)
        return obj
    
    def get_serializer_class(self):
        if self.action == 'list':
            return EventListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return EventCreateUpdateSerializer
        return EventSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by public status
        if not self.request.user.is_authenticated:
            queryset = queryset.filter(is_public=True)
        
        # Filter by organizer
        organizer_id = self.request.query_params.get('organizer')
        if organizer_id:
            queryset = queryset.filter(organizer_id=organizer_id)
        
        # Filter by virtual/physical
        is_virtual = self.request.query_params.get('is_virtual')
        if is_virtual is not None:
            queryset = queryset.filter(is_virtual=is_virtual.lower() == 'true')
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(start_datetime__gte=start_date)
        if end_date:
            queryset = queryset.filter(end_datetime__lte=end_date)
        
        return queryset
    
    def perform_create(self, serializer):
        """Set the organizer to the current user"""
        serializer.save(organizer=self.request.user)
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming events"""
        now = timezone.now()
        events = self.get_queryset().filter(
            start_datetime__gt=now
        ).order_by('start_datetime')
        
        page = self.paginate_queryset(events)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(events, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def past(self, request):
        """Get past events"""
        now = timezone.now()
        events = self.get_queryset().filter(
            end_datetime__lt=now
        ).order_by('-end_datetime')
        
        page = self.paginate_queryset(events)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(events, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_events(self, request):
        """Get current user's events"""
        events = self.get_queryset().filter(organizer=request.user)
        
        page = self.paginate_queryset(events)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(events, many=True)
        return Response(serializer.data)
