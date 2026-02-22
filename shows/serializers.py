from rest_framework import serializers
from .models import Show, ShowEpisode, Tag, ShowReminder, GuestRequest
from django.contrib.auth import get_user_model

User = get_user_model()


class TagSerializer(serializers.ModelSerializer):
    """Serializer for tags"""
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']
        read_only_fields = ['id', 'slug']


class ShowCreatorSerializer(serializers.ModelSerializer):
    """Lightweight creator info for nested serialization"""
    class Meta:
        model = User
        fields = ['id', 'username', 'profile_picture', 'is_verified']
        read_only_fields = fields


class ShowEpisodeSerializer(serializers.ModelSerializer):
    """Serializer for show episodes"""
    class Meta:
        model = ShowEpisode
        fields = [
            'id', 'show', 'episode_number', 'title', 'description',
            'air_date', 'duration', 'video_url', 'created_at'
        ]
        read_only_fields = ['created_at']


class ShowSerializer(serializers.ModelSerializer):
    """Full show serializer with creator info and engagement counts"""
    creator = ShowCreatorSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    guests = ShowCreatorSerializer(many=True, read_only=True)
    co_hosts = ShowCreatorSerializer(many=True, read_only=True)
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    schedule_display = serializers.CharField(source='get_schedule_display', read_only=True)
    episodes = ShowEpisodeSerializer(many=True, read_only=True)
    
    class Meta:
        model = Show
        fields = [
            'id', 'slug', 'title', 'description', 'thumbnail', 'creator', 'tags', 'guests', 'co_hosts',
            'external_link', 'link_platform',
            'is_recurring', 'recurrence_type', 'day_of_week', 'scheduled_time', 'schedule_display',
            'status', 'created_at', 'updated_at',
            'like_count', 'comment_count', 'share_count', 'episodes'
        ]
        read_only_fields = ['created_at', 'updated_at', 'creator', 'slug', 'share_count']
    
    def get_like_count(self, obj):
        """Get like count from annotation"""
        # CRITICAL: Check if annotation exists AND is not None
        # hasattr() returns True even if value is None/0
        return getattr(obj, '_like_count', obj.likes.count())
    
    def get_comment_count(self, obj):
        """Get comment count from annotation"""
        # CRITICAL: Check if annotation exists AND is not None
        # hasattr() returns True even if value is None/0
        return getattr(obj, '_comment_count', obj.comments.count())
    
    def validate(self, data):
        """Validate recurring show fields"""
        is_recurring = data.get('is_recurring', False)
        recurrence_type = data.get('recurrence_type')
        day_of_week = data.get('day_of_week')
        scheduled_time = data.get('scheduled_time')
        
        if is_recurring:
            if not recurrence_type:
                raise serializers.ValidationError(
                    "Recurring shows must have a 'recurrence_type'."
                )
            if not scheduled_time:
                raise serializers.ValidationError(
                    "Recurring shows must have a 'scheduled_time'."
                )
            
            # If recurrence_type is SPECIFIC_DAY, day_of_week must be set
            if recurrence_type == 'SPECIFIC_DAY' and day_of_week is None:
                raise serializers.ValidationError(
                    "Shows with recurrence_type='SPECIFIC_DAY' must specify a 'day_of_week' (0-6 for Monday-Sunday)."
                )
        
        return data


class ShowListSerializer(serializers.ModelSerializer):
    """Lightweight show serializer for list views"""
    creator = ShowCreatorSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    guests = ShowCreatorSerializer(many=True, read_only=True)
    co_hosts = ShowCreatorSerializer(many=True, read_only=True)
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    schedule_display = serializers.CharField(source='get_schedule_display', read_only=True)
    
    class Meta:
        model = Show
        fields = [
            'id', 'slug', 'title', 'description', 'thumbnail', 'creator', 'tags', 'guests', 'co_hosts',
            'external_link', 'link_platform',
            'is_recurring', 'recurrence_type', 'day_of_week', 'scheduled_time', 'schedule_display',
            'status', 'created_at', 'like_count', 'comment_count', 'share_count'
        ]
        read_only_fields = fields
    
    def get_like_count(self, obj):
        """Get like count from annotation"""
        return getattr(obj, '_like_count', obj.likes.count())
    
    def get_comment_count(self, obj):
        """Get comment count from annotation"""
        return getattr(obj, '_comment_count', obj.comments.count())


class ShowCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating shows"""
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of tag IDs to assign to this show"
    )
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=50),
        write_only=True,
        required=False,
        help_text="List of tag names to create/assign (alternative to tag_ids)"
    )
    co_host_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of user IDs to assign as co-hosts"
    )
    
    class Meta:
        model = Show
        fields = [
            'title', 'description', 'thumbnail',
            'external_link', 'link_platform',
            'is_recurring', 'recurrence_type', 'day_of_week', 'scheduled_time',
            'status', 'tag_ids', 'tag_names', 'co_host_ids'
        ]
    
    def validate(self, data):
        """Validate recurring show fields"""
        is_recurring = data.get('is_recurring', False)
        recurrence_type = data.get('recurrence_type')
        day_of_week = data.get('day_of_week')
        scheduled_time = data.get('scheduled_time')
        
        if is_recurring:
            if not recurrence_type:
                raise serializers.ValidationError(
                    "Recurring shows must have a 'recurrence_type'."
                )
            if not scheduled_time:
                raise serializers.ValidationError(
                    "Recurring shows must have a 'scheduled_time'."
                )
            
            # If recurrence_type is SPECIFIC_DAY, day_of_week must be set
            if recurrence_type == 'SPECIFIC_DAY' and day_of_week is None:
                raise serializers.ValidationError(
                    "Shows with recurrence_type='SPECIFIC_DAY' must specify a 'day_of_week' (0-6 for Monday-Sunday)."
                )
        
        return data
    
    def create(self, validated_data):
        """Create show with tags and co-hosts"""
        # Extract tags and co-hosts
        tag_ids = validated_data.pop('tag_ids', None)
        tag_names = validated_data.pop('tag_names', None)
        co_host_ids = validated_data.pop('co_host_ids', None)
        
        # Create show
        show = Show.objects.create(**validated_data)
        
        # Handle tag IDs
        if tag_ids is not None:
            show.tags.set(tag_ids)
        
        # Handle tag names (create if needed)
        if tag_names is not None:
            from .models import Tag
            for tag_name in tag_names:
                tag, created = Tag.objects.get_or_create(
                    name=tag_name,
                    defaults={'slug': tag_name.lower().replace(' ', '-')}
                )
                show.tags.add(tag)
        
        # Handle co-hosts
        if co_host_ids is not None:
            show.co_hosts.set(co_host_ids)
            # Send notifications to co-hosts
            from users.models import Notification
            from django.contrib.contenttypes.models import ContentType
            show_ct = ContentType.objects.get_for_model(Show)
            for uid in co_host_ids:
                try:
                    user = User.objects.get(id=uid)
                    Notification.objects.create(
                        recipient=user,
                        actor=show.creator,
                        notification_type='co_host_added',
                        content_type=show_ct,
                        object_id=show.id
                    )
                except User.DoesNotExist:
                    pass
        
        return show
    
    def update(self, instance, validated_data):
        """Update show with tags and co-hosts"""
        # Extract tags and co-hosts
        tag_ids = validated_data.pop('tag_ids', None)
        tag_names = validated_data.pop('tag_names', None)
        co_host_ids = validated_data.pop('co_host_ids', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Handle tag IDs
        if tag_ids is not None:
            instance.tags.set(tag_ids)
        
        # Handle tag names
        if tag_names is not None:
            from .models import Tag
            instance.tags.clear()  # Clear existing if tag_names provided
            for tag_name in tag_names:
                tag, created = Tag.objects.get_or_create(
                    name=tag_name,
                    defaults={'slug': tag_name.lower().replace(' ', '-')}
                )
                instance.tags.add(tag)
        
        # Handle co-hosts
        if co_host_ids is not None:
            # Find newly added co-hosts to notify them
            current_co_host_ids = set(instance.co_hosts.values_list('id', flat=True))
            new_co_host_ids = set(co_host_ids) - current_co_host_ids
            
            instance.co_hosts.set(co_host_ids)
            
            # Send notifications to newly added co-hosts
            if new_co_host_ids:
                from users.models import Notification
                from django.contrib.contenttypes.models import ContentType
                show_ct = ContentType.objects.get_for_model(Show)
                for uid in new_co_host_ids:
                    try:
                        user = User.objects.get(id=uid)
                        Notification.objects.create(
                            recipient=user,
                            actor=instance.creator,
                            notification_type='co_host_added',
                            content_type=show_ct,
                            object_id=instance.id
                        )
                    except User.DoesNotExist:
                        pass
        
        return instance


class ShowReminderSerializer(serializers.ModelSerializer):
    """Serializer for show reminders"""
    show_title = serializers.CharField(source='show.title', read_only=True)
    show_id = serializers.IntegerField(source='show.id', read_only=True)
    
    class Meta:
        model = ShowReminder
        fields = [
            'id', 'show', 'show_id', 'show_title', 'scheduled_for',
            'reminder_sent_at', 'creator_response', 'responded_at', 'created_at'
        ]
        read_only_fields = ['id', 'reminder_sent_at', 'created_at']


class GuestRequestSerializer(serializers.ModelSerializer):
    """Serializer for guest requests with full details"""
    requester = ShowCreatorSerializer(read_only=True)
    show = ShowListSerializer(read_only=True)
    
    class Meta:
        model = GuestRequest
        fields = ['id', 'show', 'requester', 'status', 'message', 'created_at', 'updated_at']
        read_only_fields = ['status', 'created_at', 'updated_at']


class GuestRequestCreateSerializer(serializers.Serializer):
    """Serializer for creating guest requests"""
    show_id = serializers.IntegerField()
    message = serializers.CharField(max_length=500, required=False, allow_blank=True)
    
    def validate_show_id(self, value):
        """Validate show exists"""
        if not Show.objects.filter(id=value).exists():
            raise serializers.ValidationError("Show does not exist.")
        return value


class GuestRequestListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing guest requests"""
    requester = ShowCreatorSerializer(read_only=True)
    show = ShowListSerializer(read_only=True)
    
    class Meta:
        model = GuestRequest
        fields = [
            'id', 'show', 'requester', 'status', 'message', 'created_at'
        ]
        read_only_fields = fields
