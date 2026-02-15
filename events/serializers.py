from rest_framework import serializers
from .models import Event
from django.contrib.auth import get_user_model

User = get_user_model()


class EventOrganizerSerializer(serializers.ModelSerializer):
    """Lightweight organizer info for nested serialization"""
    class Meta:
        model = User
        fields = ['id', 'username', 'profile_picture', 'is_verified']
        read_only_fields = fields


class EventSerializer(serializers.ModelSerializer):
    """Full event serializer"""
    organizer = EventOrganizerSerializer(read_only=True)
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    is_ongoing = serializers.BooleanField(read_only=True)
    is_past = serializers.BooleanField(read_only=True)
    schedule_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'description', 'banner_image',
            'organizer', 'start_datetime', 'end_datetime',
            'venue_name', 'address', 'is_virtual', 'meeting_link',
            'capacity', 'registration_link', 'registration_deadline',
            'is_public', 'is_recurring', 'recurrence_type',
            'day_of_week', 'scheduled_time',
            'created_at', 'updated_at',
            'like_count', 'comment_count', 'share_count',
            'status', 'is_upcoming', 'is_ongoing', 'is_past',
            'schedule_display'
        ]
        read_only_fields = ['organizer', 'created_at', 'updated_at']
    
    def get_like_count(self, obj):
        """Get like count from annotation or property"""
        # Use the renamed annotation to avoid conflict with model property
        return getattr(obj, '_like_count', obj.like_count)
    
    def get_comment_count(self, obj):
        """Get comment count from annotation or property"""
        # Use the renamed annotation to avoid conflict with model property
        return getattr(obj, '_comment_count', obj.comment_count)
    
    def validate(self, data):
        """Validate event dates"""
        start_datetime = data.get('start_datetime')
        end_datetime = data.get('end_datetime')
        
        if start_datetime and end_datetime:
            if end_datetime <= start_datetime:
                raise serializers.ValidationError(
                    "End date/time must be after start date/time."
                )
        
        # Validate virtual event has meeting link
        if data.get('is_virtual') and not data.get('meeting_link'):
            raise serializers.ValidationError(
                "Virtual events must have a meeting link."
            )
        
        return data
    
    def get_schedule_display(self, obj):
        return obj.get_schedule_display()


class EventListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    organizer = EventOrganizerSerializer(read_only=True)
    like_count = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)
    
    def get_like_count(self, obj):
        """Get like count from annotation or property"""
        # Use the renamed annotation to avoid conflict with model property
        return getattr(obj, '_like_count', obj.like_count)
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'banner_image', 'organizer',
            'start_datetime', 'end_datetime', 'venue_name',
            'is_virtual', 'is_public',
            'is_recurring', 'recurrence_type', 'day_of_week', 'scheduled_time',
            'status', 'like_count', 'share_count'
        ]
        read_only_fields = fields


class EventCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating events"""
    start_datetime = serializers.DateTimeField(required=False, allow_null=True)
    end_datetime = serializers.DateTimeField(required=False, allow_null=True)
    
    class Meta:
        model = Event
        fields = [
            'title', 'description', 'banner_image',
            'start_datetime', 'end_datetime',
            'venue_name', 'address', 'is_virtual', 'meeting_link',
            'capacity', 'registration_link', 'registration_deadline',
            'is_public', 'is_recurring', 'recurrence_type',
            'day_of_week', 'scheduled_time'
        ]
    
    def validate(self, data):
        """Validate event based on whether it's recurring or one-off"""
        is_recurring = data.get('is_recurring', False)
        
        if is_recurring:
            # Recurring events need recurrence_type and scheduled_time
            if not data.get('recurrence_type'):
                raise serializers.ValidationError(
                    "Recurring events must have a recurrence type."
                )
            if not data.get('scheduled_time'):
                raise serializers.ValidationError(
                    "Recurring events must have a scheduled time."
                )
            if data.get('recurrence_type') == 'SPECIFIC_DAY' and data.get('day_of_week') is None:
                raise serializers.ValidationError(
                    "Specific day recurrence requires a day_of_week."
                )
        else:
            # One-off events need start_datetime
            if not data.get('start_datetime'):
                raise serializers.ValidationError(
                    "One-off events must have a start date/time."
                )
        
        # Validate date ordering if both are provided
        start_datetime = data.get('start_datetime')
        end_datetime = data.get('end_datetime')
        if start_datetime and end_datetime:
            if end_datetime <= start_datetime:
                raise serializers.ValidationError(
                    "End date/time must be after start date/time."
                )
        
        return data
