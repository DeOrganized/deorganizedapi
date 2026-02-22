from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Post

User = get_user_model()


class PostAuthorSerializer(serializers.ModelSerializer):
    """Lightweight author info for post cards"""
    class Meta:
        model = User
        fields = ['id', 'username', 'profile_picture', 'is_verified', 'role']
        read_only_fields = fields


class PostSerializer(serializers.ModelSerializer):
    """Full post serializer with engagement data"""
    author = PostAuthorSerializer(read_only=True)
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    user_has_liked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'id', 'author', 'content', 'image', 'is_pinned',
            'created_at', 'updated_at',
            'like_count', 'comment_count', 'user_has_liked'
        ]
        read_only_fields = ['id', 'author', 'created_at', 'updated_at']

    def get_like_count(self, obj):
        return getattr(obj, '_like_count', obj.like_count)

    def get_comment_count(self, obj):
        return getattr(obj, '_comment_count', obj.comment_count)

    def get_user_has_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Use prefetched data if available
            if hasattr(obj, '_user_has_liked'):
                return obj._user_has_liked
            return obj.likes.filter(user=request.user).exists()
        return False


class PostCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/editing posts"""
    class Meta:
        model = Post
        fields = ['content', 'image']

    def validate_content(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Post content cannot be empty.")
        return value.strip()
