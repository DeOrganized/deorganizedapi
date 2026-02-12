from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta, datetime
from .models import Show, ShowEpisode, Tag, ShowReminder, GuestRequest
from users.models import Notification
from .serializers import (
    ShowSerializer, ShowListSerializer, ShowCreateSerializer,
    ShowEpisodeSerializer, TagSerializer, ShowReminderSerializer,
    GuestRequestSerializer, GuestRequestCreateSerializer, GuestRequestListSerializer
)
from api.permissions import IsCreatorOrReadOnly


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Tag model - read-only.
    
    List: GET /api/tags/
    Retrieve: GET /api/tags/{id}/
    Search: GET /api/tags/?search=crypto
    """
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering = ['name']


class ShowViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Show model with creator-only creation.
    
    List: GET /api/shows/
    Create: POST /api/shows/ (creators only)
    Retrieve: GET /api/shows/{id}/
    Update: PUT/PATCH /api/shows/{id}/ (owner only)
    Delete: DELETE /api/shows/{id}/ (owner only)
    
    Custom actions:
    - upcoming_shows: GET /api/shows/upcoming_shows/
    - my_shows: GET /api/shows/my_shows/
    
    Filters:
    - ?search=query - Search title and description
    - ?tags=1,2,3 - Filter by tag IDs
    - ?creator=15 - Filter by creator ID
    - ?status=published - Filter by status
    """
    queryset = Show.objects.select_related('creator').prefetch_related('tags').annotate(
        _like_count=Count('likes', distinct=True),
        _comment_count=Count('comments', distinct=True)
    ).prefetch_related('likes', 'comments')
    permission_classes = [IsCreatorOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'title', 'like_count']
    ordering = ['-created_at']
    lookup_field = 'slug'  # Use slug instead of pk for URLs
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ShowListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ShowCreateSerializer
        return ShowSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        else:
            # Default: only show published shows for non-owners
            if not self.request.user.is_authenticated:
                queryset = queryset.filter(status='published')
        
        # Filter by creator
        creator_id = self.request.query_params.get('creator')
        if creator_id:
            queryset = queryset.filter(creator_id=creator_id)
        
        # Filter by tags (comma-separated tag IDs)
        tags_param = self.request.query_params.get('tags')
        if tags_param:
            tag_ids = [int(tid) for tid in tags_param.split(',') if tid.strip().isdigit()]
            if tag_ids:
                # Show must have ALL specified tags
                for tag_id in tag_ids:
                    queryset = queryset.filter(tags__id=tag_id)
        
        # Filter by recurring
        is_recurring = self.request.query_params.get('is_recurring')
        if is_recurring is not None:
            queryset = queryset.filter(is_recurring=is_recurring.lower() == 'true')
        
        # Filter by day of week
        day_of_week = self.request.query_params.get('day_of_week')
        if day_of_week is not None:
            queryset = queryset.filter(day_of_week=int(day_of_week))
        
        return queryset.distinct()  # Avoid duplicates from tag filtering
    
    def get_serializer(self, *args, **kwargs):
        """Inject request context for proper image URL generation"""
        kwargs.setdefault('context', self.get_serializer_context())
        return super().get_serializer(*args, **kwargs)
    
    def perform_create(self, serializer):
        """Set the creator to the current user"""
        serializer.save(creator=self.request.user)
    
    @action(detail=False, methods=['get'])
    def upcoming_shows(self, request):
        """Get all published recurring shows with counts"""
        # get_queryset() already has annotations from base queryset
        shows = self.get_queryset().filter(
            is_recurring=True,
            status='published'
        )
        serializer = self.get_serializer(shows, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_shows(self, request):
        """Get current user's shows with counts"""
        # get_queryset() already has annotations from base queryset
        shows = self.get_queryset().filter(creator=request.user)
        serializer = self.get_serializer(shows, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def respond_to_reminder(self, request, slug=None):
        """Respond to show reminder (confirm or cancel)"""
        show = self.get_object()
        
        # Verify user is the creator
        if show.creator != request.user:
            return Response(
                {'error': 'Only the show creator can respond to reminders'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        scheduled_for_str = request.data.get('scheduled_for')
        response_type = request.data.get('response')  # 'confirmed' or 'cancelled'
        
        if not scheduled_for_str or response_type not in ['confirmed', 'cancelled']:
            return Response(
                {'error': 'Invalid request. Provide `scheduled_for` and `response` (confirmed/cancelled)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Parse the datetime
            scheduled_for = datetime.fromisoformat(scheduled_for_str.replace('Z', '+00:00'))
            if timezone.is_naive(scheduled_for):
                scheduled_for = timezone.make_aware(scheduled_for)
            
            reminder = ShowReminder.objects.get(
                show=show,
                scheduled_for=scheduled_for
            )
            
            reminder.creator_response = response_type.upper()
            reminder.responded_at = timezone.now()
            reminder.save()
            
            # If cancelled, add to cancelled_instances
            if response_type == 'cancelled':
                date_str = scheduled_for.date().isoformat()
                if date_str not in show.cancelled_instances:
                    show.cancelled_instances.append(date_str)
                    show.save(update_fields=['cancelled_instances'])
                
                # Create confirmation notification
                Notification.objects.create(
                    recipient=request.user,
                    actor=request.user,  # Self-notification
                    notification_type='show_cancelled',
                    content_type=None,
                    object_id=None
                )
            
            return Response(ShowReminderSerializer(reminder).data)
        
        except ShowReminder.DoesNotExist:
            return Response(
                {'error': 'Reminder not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except (ValueError, TypeError) as e:
            return Response(
                {'error': f'Invalid datetime format: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], permission_classes=[])
    def track_share(self, request, slug=None):
        """Track when a show is shared - increments share_count"""
        show = self.get_object()
        show.share_count += 1
        show.save(update_fields=['share_count'])
        
        return Response({
            'success': True,
            'share_count': show.share_count
        })
    
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def upcoming_instances(self, request, slug=None):
        """Get upcoming instances of a recurring show"""
        show = self.get_object()
        
        if not show.is_recurring:
            return Response(
                {'error': 'Not a recurring show'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate next 30 days of instances
        instances = []
        today = timezone.now().date()
        
        for i in range(30):
            date = today + timedelta(days=i)
            
            # Check if this date matches the recurrence pattern
            if show.should_air_on_date(date):
                # Check if there's a reminder for this instance
                scheduled_datetime = timezone.make_aware(
                    datetime.combine(date, show.scheduled_time)
                )
                
                try:
                    reminder = ShowReminder.objects.get(
                        show=show,
                        scheduled_for=scheduled_datetime
                    )
                    reminder_status = reminder.creator_response
                except ShowReminder.DoesNotExist:
                    reminder_status = None
                
                instances.append({
                    'date': date.isoformat(),
                    'time': show.scheduled_time.isoformat(),
                    'datetime': scheduled_datetime.isoformat(),
                    'status': 'scheduled',
                    'reminder_status': reminder_status
                })
        
        return Response(instances)


class ShowEpisodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ShowEpisode model.
    """
    queryset = ShowEpisode.objects.select_related('show', 'show__creator')
    serializer_class = ShowEpisodeSerializer
    permission_classes = [IsCreatorOrReadOnly]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['air_date', 'episode_number']
    ordering = ['episode_number']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by show
        show_id = self.request.query_params.get('show')
        if show_id:
            queryset = queryset.filter(show_id=show_id)
        
        return queryset
    
    def perform_create(self, serializer):
        """Ensure the user owns the show before creating episodes"""
        show = serializer.validated_data['show']
        if show.creator != self.request.user:
            raise PermissionError("You can only create episodes for your own shows.")
        serializer.save()


class GuestRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for GuestRequest model.
    
    List: GET /api/shows/guest-requests/
    Create: POST /api/shows/guest-requests/create_request/
    Retrieve: GET /api/shows/guest-requests/{id}/
    Accept: POST /api/shows/guest-requests/{id}/accept/
    Decline: POST /api/shows/guest-requests/{id}/decline/
    
    Filters:
    - ?received=true - Get requests received for my shows
    - Default: Get requests I've sent
    """
    queryset = GuestRequest.objects.all()  # Base queryset for detail actions
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'create_request':
            return GuestRequestCreateSerializer
        elif self.action == 'list':
            return GuestRequestListSerializer
        return GuestRequestSerializer
    
    def get_queryset(self):
        """Filter requests based on user role - only for list actions"""
        # Don't filter for detail actions (retrieve, accept, decline)
        if self.action in ['retrieve', 'accept', 'decline']:
            return GuestRequest.objects.select_related('requester', 'show', 'show__creator')
        
        user = self.request.user
        
        # Show requests I've received (for shows I own)
        if self.request.query_params.get('received') == 'true':
            return GuestRequest.objects.filter(
                show__creator=user,
                status='pending'
            ).select_related('requester', 'show').order_by('-created_at')
        
        # Show requests I've sent
        return GuestRequest.objects.filter(
            requester=user
        ).select_related('show', 'show__creator').order_by('-created_at')

    
    @action(detail=False, methods=['post'])
    def create_request(self, request):
        """Create a guest request"""
        serializer = GuestRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        show_id = serializer.validated_data['show_id']
        message = serializer.validated_data.get('message', '')
        
        # Validate user is a creator
        if request.user.role != 'creator':
            return Response(
                {'error': 'Only creators can request guest appearances'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            show = Show.objects.get(id=show_id)
        except Show.DoesNotExist:
            return Response(
                {'error': 'Show not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Can't request guest spot on own show
        if show.creator == request.user:
            return Response(
                {'error': 'Cannot request guest spot on your own show'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if request already exists
        if GuestRequest.objects.filter(show=show, requester=request.user).exists():
            return Response(
                {'error': 'You already have a request for this show'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create guest request
        guest_request = GuestRequest.objects.create(
            show=show,
            requester=request.user,
            message=message
        )
        
        # Create notification for show owner
        Notification.objects.create(
            recipient=show.creator,
            message=f"{request.user.username} wants to be on your show",
            actor=request.user,
            notification_type='guest_request',
            content_type_id=guest_request.pk,
            object_id=show.id
        )
        
        return Response(
            GuestRequestSerializer(guest_request).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Accept a guest request"""
        try:
            guest_request = self.get_object()
        except GuestRequest.DoesNotExist:
            return Response(
                {'error': 'Guest request not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Only show creator can accept
        if guest_request.show.creator != request.user:
            return Response(
                {'error': 'Only the show creator can accept requests'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Update status
        guest_request.status = 'accepted'
        guest_request.save()
        
        # Add requester as guest
        guest_request.show.guests.add(guest_request.requester)
        
        # Create notification for requester
        Notification.objects.create(
            recipient=guest_request.requester,
            actor=request.user,
            notification_type='guest_accepted',
            content_type_id=guest_request.pk,
            object_id=guest_request.show.id
        )
        
        return Response(GuestRequestSerializer(guest_request).data)
    
    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        """Decline a guest request"""
        try:
            guest_request = self.get_object()
        except GuestRequest.DoesNotExist:
            return Response(
                {'error': 'Guest request not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Only show creator can decline
        if guest_request.show.creator != request.user:
            return Response(
                {'error': 'Only the show creator can decline requests'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Update status
        guest_request.status = 'declined'
        guest_request.save()
        
        # Create notification for requester
        Notification.objects.create(
            recipient=guest_request.requester,
            actor=request.user,
            notification_type='guest_declined',
            content_type_id=guest_request.pk,
            object_id=guest_request.show.id
        )
        
        return Response(GuestRequestSerializer(guest_request).data)
