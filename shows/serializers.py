from rest_framework import serializers
from .models import Show, ShowEpisode, Tag, ShowReminder
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
    schedule_display = serializers.CharField(source='get_schedule_display', read_only=True)
    episodes = ShowEpisodeSerializer(many=True, read_only=True)
    
    class Meta:
        model = Show
        fields = [
            'id', 'slug', 'title', 'description', 'thumbnail', 'creator', 'tags',
            'external_link', 'link_platform',
            'is_recurring', 'recurrence_type', 'day_of_week', 'scheduled_time', 'schedule_display',
            'status', 'created_at', 'updated_at',
            'like_count', 'comment_count', 'share_count', 'episodes'
        ]
        read_only_fields = ['created_at', 'updated_at', 'creator', 'slug', 'share_count', 'like_count', 'comment_count']
    
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
            if recurrence_type == 'SPECIFIC_DAY' and day_of_week is None:
                raise serializers.ValidationError(
                    "SPECIFIC_DAY recurrence requires 'day_of_week' to be set."
                )
        
        return data


class ShowListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    creator = ShowCreatorSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    schedule_display = serializers.CharField(source='get_schedule_display', read_only=True)
    
    class Meta:
        model = Show
        fields = [
            'id', 'slug', 'title', 'description', 'thumbnail', 'creator', 'tags',
            'external_link', 'link_platform',
            'is_recurring', 'recurrence_type', 'day_of_week', 'status',
            'created_at', 'like_count', 'comment_count', 'share_count', 'schedule_display'
        ]
        read_only_fields = fields


class ShowCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating shows"""
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = Show
        fields = [
            'title', 'description', 'thumbnail',
            'external_link', 'link_platform', 'tag_ids',
            'is_recurring', 'recurrence_type', 'day_of_week', 'scheduled_time', 'status'
        ]
    
    def validate(self, data):
        """Validate recurring show fields"""
        # For updates, merge with existing instance data
        if self.instance:
            is_recurring = data.get('is_recurring', self.instance.is_recurring)
            recurrence_type = data.get('recurrence_type', self.instance.recurrence_type)
            day_of_week = data.get('day_of_week', self.instance.day_of_week)
            scheduled_time = data.get('scheduled_time', self.instance.scheduled_time)
        else:
            is_recurring = data.get('is_recurring', False)
            recurrence_type = data.get('recurrence_type')
            day_of_week = data.get('day_of_week')
            scheduled_time = data.get('scheduled_time')
        
        # Treat empty string as None
        if recurrence_type == '':
            recurrence_type = None
        
        if is_recurring:
            if not recurrence_type:
                raise serializers.ValidationError({
                    'recurrence_type': "Recurring shows must have a 'recurrence_type'."
                })
            if not scheduled_time:
                raise serializers.ValidationError({
                    'scheduled_time': "Recurring shows must have a 'scheduled_time'."
                })
            if recurrence_type == 'SPECIFIC_DAY' and day_of_week is None:
                raise serializers.ValidationError({
                    'day_of_week': "SPECIFIC_DAY recurrence requires 'day_of_week' to be set."
                })
        
        return data
    
    def create(self, validated_data):
        """Create show and assign tags"""
        tag_ids = validated_data.pop('tag_ids', [])
        show = Show.objects.create(**validated_data)
        
        if tag_ids:
            show.tags.set(tag_ids)
        
        return show
    
    def update(self, instance, validated_data):
        """Update show and reassign tags"""
        tag_ids = validated_data.pop('tag_ids', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if tag_ids is not None:
            instance.tags.set(tag_ids)
        
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
