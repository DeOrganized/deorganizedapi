from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import Like, Comment, Follow, Notification, RTMPDestination, Subscription
from django.contrib.contenttypes.models import ContentType

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Public user profile serializer — no PII."""
    follower_count = serializers.IntegerField(read_only=True)
    following_count = serializers.IntegerField(read_only=True)
    is_creator = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'display_name',
            'role', 'stacks_address', 'bio', 'profile_picture', 'cover_photo',
            'website', 'twitter', 'instagram', 'youtube',
            'is_verified', 'date_joined',
            'follower_count', 'following_count', 'is_creator',
        ]
        read_only_fields = ['id', 'date_joined', 'is_verified']


class PrivateUserSerializer(UserSerializer):
    """Authenticated user's own profile — includes PII fields not shown publicly."""

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + [
            'email', 'first_name', 'last_name', 'is_staff',
        ]


class UserListSerializer(serializers.ModelSerializer):
    """Lightweight user serializer for lists — public fields only."""
    is_creator = serializers.BooleanField(read_only=True)
    follower_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'profile_picture',
            'role', 'is_verified', 'is_creator', 'follower_count', 'bio',
            'stacks_address', 'date_joined',
        ]
        read_only_fields = fields


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'password2',
            'first_name', 'last_name', 'role'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': False},
            'last_name': {'required': False},
        }
    
    def validate(self, data):
        """Validate passwords match"""
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Passwords must match."})
        return data
    
    def create(self, validated_data):
        """Create user with hashed password"""
        validated_data.pop('password2')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=validated_data.get('role', 'user')
        )
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile"""
    
    class Meta:
        model = User
        fields = [
            'username', 'display_name', 'bio', 'profile_picture', 'cover_photo',
            'website', 'twitter', 'instagram', 'youtube', 'role'
        ]
    
    def validate_role(self, value):
        """Only allow upgrading from user to creator, not downgrading"""
        user = self.instance
        if user and user.role == 'creator' and value == 'user':
            raise serializers.ValidationError(
                "Cannot downgrade from creator to user role."
            )
        return value
    
    def validate_username(self, value):
        """Ensure username is unique (excluding current user)"""
        user = self.instance
        if User.objects.exclude(pk=user.pk).filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value


class LikeSerializer(serializers.ModelSerializer):
    """Serializer for likes"""
    user = UserListSerializer(read_only=True)
    
    class Meta:
        model = Like
        fields = ['id', 'user', 'content_type', 'object_id', 'created_at']
        read_only_fields = ['created_at']


class CommentSerializer(serializers.ModelSerializer):
    """Serializer for comments with nested reply support"""
    user = UserListSerializer(read_only=True)
    reply_count = serializers.IntegerField(read_only=True)
    replies = serializers.SerializerMethodField()
    
    class Meta:
        model = Comment
        fields = [
            'id', 'user', 'text', 'parent',
            'content_type', 'object_id',
            'created_at', 'updated_at',
            'reply_count', 'replies'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_replies(self, obj):
        """Get nested replies (one level deep)"""
        if obj.parent is None:
            replies = obj.replies.all()[:5]  # Limit to 5 most recent
            return CommentSerializer(replies, many=True, context=self.context).data
        return []


class CommentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating comments"""
    class Meta:
        model = Comment
        fields = ['text', 'parent', 'content_type', 'object_id']


class FollowSerializer(serializers.ModelSerializer):
    """Serializer for follow relationships"""
    follower = UserListSerializer(read_only=True)
    following = UserListSerializer(read_only=True)
    
    class Meta:
        model = Follow
        fields = ['id', 'follower', 'following', 'created_at']
        read_only_fields = ['created_at']


class CreatorProfileSerializer(serializers.ModelSerializer):
    """Extended public profile for creators with their shows — no PII."""
    follower_count = serializers.IntegerField(read_only=True)
    following_count = serializers.IntegerField(read_only=True)
    show_count = serializers.IntegerField(source='shows.count', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'display_name',
            'role', 'bio', 'profile_picture', 'cover_photo',
            'website', 'twitter', 'instagram', 'youtube',
            'is_verified', 'date_joined',
            'follower_count', 'following_count', 'show_count',
        ]
        read_only_fields = fields



# ============================================
# WALLET AUTHENTICATION SERIALIZERS (Production)
# Nonce-based authentication with signature verification
# ============================================

class WalletNonceRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting an authentication nonce.
    
    Used in POST /api/auth/wallet/nonce/
    """
    wallet_address = serializers.CharField(max_length=255, required=True)
    
    def validate_wallet_address(self, value):
        """Validate Stacks wallet address format"""
        if not value:
            raise serializers.ValidationError('Wallet address is required')
        
        # Stacks addresses start with SP (mainnet) or ST (testnet)
        if not (value.startswith('SP') or value.startswith('ST')):
            raise serializers.ValidationError(
                'Invalid Stacks address format. Must start with SP or ST.'
            )
        
        # Basic length validation (Stacks addresses are ~40-42 chars)
        if len(value) < 38 or len(value) > 45:
            raise serializers.ValidationError('Invalid Stacks address length')
        
        return value


class WalletSignatureVerifySerializer(serializers.Serializer):
    """
    Serializer for verifying wallet signature and authenticating.
    
    Used in POST /api/auth/wallet/verify/
    """
    wallet_address = serializers.CharField(max_length=255, required=True)
    signature = serializers.CharField(required=True)
    message = serializers.CharField(required=True)
    
    def validate_wallet_address(self, value):
        """Validate Stacks wallet address format"""
        if not value:
            raise serializers.ValidationError('Wallet address is required')
        
        if not (value.startswith('SP') or value.startswith('ST')):
            raise serializers.ValidationError('Invalid Stacks address format')
        
        return value
    
    def validate_signature(self, value):
        """Validate signature is present and non-empty"""
        if not value or len(value) < 64:
            raise serializers.ValidationError(
                'Invalid signature format. Signature appears too short.'
            )
        return value
    
    def validate_message(self, value):
        """Validate message is present"""
        if not value:
            raise serializers.ValidationError('Message is required')
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        # Ensure message contains the wallet address (anti-phishing)
        if data['wallet_address'] not in data['message']:
            raise serializers.ValidationError({
                'message': 'Message must contain the wallet address'
            })
        
        # Ensure message contains word "Nonce" (our format check)
        if 'Nonce:' not in data['message']:
            raise serializers.ValidationError({
                'message': 'Message must contain a nonce'
            })
        
        return data



class WalletUserSerializer(serializers.ModelSerializer):
    """
    Serializer for wallet-authenticated users.
    Used in authentication responses.
    """
    is_new = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'stacks_address', 'role',
            'bio', 'profile_picture', 'website',
            'is_verified', 'date_joined', 'is_new'
        ]
        read_only_fields = fields


# ============================================
# DEFERRED USER CREATION SERIALIZERS
# ============================================
# NOTE: These do NOT verify wallet signatures
# Acceptable for MVP/testing only

class WalletLoginOrCheckSerializer(serializers.Serializer):
    """
    Serializer for checking if wallet exists and logging in.
    
    Used in POST /api/users/wallet-login-or-check/
    """
    wallet_address = serializers.CharField(max_length=255, required=True)
    
    def validate_wallet_address(self, value):
        """Validate Stacks wallet address format"""
        if not value:
            raise serializers.ValidationError('Wallet address is required')
        
        # Stacks addresses start with SP (mainnet) or ST (testnet)
        if not (value.startswith('SP') or value.startswith('ST')):
            raise serializers.ValidationError(
                'Invalid Stacks address format. Must start with SP or ST.'
            )
        
        # Basic length validation (Stacks addresses are ~40-42 chars)
        if len(value) < 38 or len(value) > 45:
            raise serializers.ValidationError('Invalid Stacks address length')
        
        return value


class CompleteSetupSerializer(serializers.Serializer):
    """
    Serializer for completing user setup after wallet connection.
    
    Used in POST /api/users/complete-setup/
    """
    wallet_address = serializers.CharField(max_length=255, required=True)
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    display_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=['user', 'creator'], default='user')
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    bio = serializers.CharField(max_length=500, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)
    twitter = serializers.CharField(max_length=100, required=False, allow_blank=True)
    instagram = serializers.CharField(max_length=100, required=False, allow_blank=True)
    youtube = serializers.URLField(required=False, allow_blank=True)
    
    def validate_wallet_address(self, value):
        """Validate Stacks wallet address format"""
        if not value:
            raise serializers.ValidationError('Wallet address is required')
        
        if not (value.startswith('SP') or value.startswith('ST')):
            raise serializers.ValidationError('Invalid Stacks address format')
        
        # Check if wallet already exists (duplicate prevention at serializer level)
        if User.objects.filter(stacks_address=value).exists():
            raise serializers.ValidationError(
                'This wallet address is already registered. Use wallet-login-or-check to login.'
            )
        
        return value
    
    def validate_username(self, value):
        """Validate username if provided"""
        if value:
            # Check if username already exists
            if User.objects.filter(username=value).exists():
                raise serializers.ValidationError('This username is already taken')
            
            # Validate username format
            import re
            if not re.match(r'^[a-zA-Z0-9_-]{3,150}$', value):
                raise serializers.ValidationError(
                    'Username must be 3-150 characters and contain only letters, numbers, underscores, and hyphens'
                )
        
        return value


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for user notifications"""
    actor = UserListSerializer(read_only=True)
    content_type_name = serializers.SerializerMethodField()
    show_slug = serializers.SerializerMethodField()
    show_title = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'actor', 'notification_type',
            'content_type', 'object_id', 'content_type_name',
            'show_slug', 'show_title', 'is_read', 'created_at'
        ]
        read_only_fields = ['id', 'recipient', 'actor', 'created_at']
    
    def get_content_type_name(self, obj):
        """Return the model name of the content type (e.g., 'show', 'post', 'event')"""
        if obj.content_type:
            return obj.content_type.model
        return None
    
    def get_show_slug(self, obj):
        """Return slug if the notification references a Show"""
        if obj.content_type and obj.content_type.model == 'show' and obj.object_id:
            try:
                from shows.models import Show
                show = Show.objects.filter(id=obj.object_id).values_list('slug', flat=True).first()
                return show
            except Exception:
                pass
        return None
    
    def get_show_title(self, obj):
        """Return title if the notification references a Show"""
        if obj.content_type and obj.content_type.model == 'show' and obj.object_id:
            try:
                from shows.models import Show
                show = Show.objects.filter(id=obj.object_id).values_list('title', flat=True).first()
                return show
            except Exception:
                pass
        return None


class RTMPDestinationSerializer(serializers.ModelSerializer):
    stream_key_masked = serializers.SerializerMethodField()

    class Meta:
        model = RTMPDestination
        fields = [
            'id', 'platform', 'stream_key', 'stream_key_masked',
            'rtmp_url', 'label', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'stream_key': {'write_only': True},  # never return raw key
        }

    def get_stream_key_masked(self, obj):
        """Return masked stream key — show only last 4 characters."""
        if obj.stream_key and len(obj.stream_key) > 4:
            return '•' * (len(obj.stream_key) - 4) + obj.stream_key[-4:]
        return '••••'


class BroadcastScheduleSerializer(serializers.Serializer):
    """Serializer for updating a creator's broadcast schedule."""
    broadcast_time = serializers.TimeField(required=False, allow_null=True)
    broadcast_days = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False, allow_empty=True
    )
    broadcast_timezone = serializers.CharField(max_length=50, required=False)


class SubscriptionSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)
    plan_display = serializers.CharField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id', 'plan', 'plan_display', 'status', 'is_active',
            'started_at', 'expires_at', 'stx_address', 'stx_tx_id'
        ]
        read_only_fields = ['id', 'started_at', 'is_active', 'plan_display']
