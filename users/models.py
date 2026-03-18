from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


class User(AbstractUser):
    """
    Custom user model with role-based access (Creator vs regular User).
    """
    ROLE_CHOICES = [
        ('user', 'User'),
        ('creator', 'Creator'),
    ]
    
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='user',
        help_text="User role: 'creator' can create shows, 'user' cannot"
    )

    stacks_address = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True, help_text="Stacks wallet address")
    
    # Display name (optional, can be different from username)
    display_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Display name shown to other users (optional)"
    )
    
    # Profile information
    bio = models.TextField(blank=True, max_length=500)
    profile_picture = models.ImageField(
        upload_to='users/profiles/',
        blank=True,
        null=True
    )
    cover_photo = models.ImageField(
        upload_to='users/covers/',
        blank=True,
        null=True
    )
    
    # Social links
    website = models.URLField(blank=True)
    twitter = models.CharField(max_length=100, blank=True)
    instagram = models.CharField(max_length=100, blank=True)
    youtube = models.URLField(blank=True)
    
    # Verification
    is_verified = models.BooleanField(default=False)

    # Broadcast schedule (for creators)
    broadcast_time = models.TimeField(
        null=True, blank=True,
        help_text="Daily broadcast start time"
    )
    broadcast_days = models.JSONField(
        default=list, blank=True,
        help_text="List of day indices (0=Mon, 6=Sun) for scheduled broadcasts"
    )
    broadcast_timezone = models.CharField(
        max_length=50, default='UTC', blank=True,
        help_text="Timezone for broadcast schedule (e.g. 'America/New_York')"
    )

    # DM pay-gate preferences (Phase 10)
    dm_paygate_enabled = models.BooleanField(
        default=False,
        help_text="If True, require x402 payment to send a DM to this creator"
    )
    dm_price_stx = models.BigIntegerField(
        default=0,
        help_text="Price in microSTX to send a DM"
    )
    dm_price_usdcx = models.BigIntegerField(
        default=0,
        help_text="Price in micro-USDCx to send a DM"
    )

    # Payout address for tips and merch (can differ from login wallet)
    payout_stx_address = models.CharField(
        max_length=255, blank=True,
        help_text="STX address for receiving payments (tips, merch). Falls back to stacks_address."
    )

    # DAPP loyalty points — awarded on verified x402 payments
    dapp_points = models.IntegerField(default=0)
    # True once stacks_address is cryptographically verified at signup
    wallet_verified = models.BooleanField(default=False)

    # The Stacks address derived from the key used to sign messages via
    # stx_signMessage. This is NOT the same as stacks_address (STX spending
    # key) — Leather signs messages with the app/data key, which has a
    # different derivation path. Stored on first verified login and used
    # to authenticate subsequent logins.
    signing_address = models.CharField(
        max_length=64, blank=True, null=True, db_index=True,
        help_text="Address recovered from the signing key (stx_signMessage). May differ from stacks_address."
    )
    
    # Timestamps
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['role', '-date_joined']),
            models.Index(fields=['is_verified']),
        ]
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    @property
    def is_creator(self):
        """Check if user has creator role"""
        return self.role == 'creator'
    
    @property
    def follower_count(self):
        """Number of users following this user"""
        return self.followers.count()
    
    @property
    def following_count(self):
        """Number of users this user is following"""
        return self.following.count()
    
    def get_liked_shows(self):
        """
        Return all shows this user has liked.
        Uses ContentType to filter likes for Show model only.
        """
        from django.contrib.contenttypes.models import ContentType
        from shows.models import Show
        
        show_content_type = ContentType.objects.get_for_model(Show)
        liked_show_ids = self.likes.filter(
            content_type=show_content_type
        ).values_list('object_id', flat=True)
        
        return Show.objects.filter(id__in=liked_show_ids)


class Like(models.Model):
    """
    Generic like model that can be applied to any content (Shows, News, Events).
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    
    # Generic foreign key to support multiple content types
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['user', 'content_type', 'object_id']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} likes {self.content_object}"


class Comment(models.Model):
    """
    Generic comment model with support for nested replies.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    
    # Generic foreign key to support multiple content types
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    text = models.TextField(max_length=1000)
    
    # Nested comments support
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='replies'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['parent']),
        ]
    
    def __str__(self):
        return f"{self.user.username}: {self.text[:50]}"
    
    @property
    def reply_count(self):
        """Number of replies to this comment"""
        return self.replies.count()


class Follow(models.Model):
    """
    Follow relationship between users.
    """
    follower = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='following'
    )
    following = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='followers'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['follower', 'following']
        indexes = [
            models.Index(fields=['follower', '-created_at']),
            models.Index(fields=['following', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"
    
    def save(self, *args, **kwargs):
        # Prevent self-following
        if self.follower == self.following:
            raise ValueError("Users cannot follow themselves")
        super().save(*args, **kwargs)


class Notification(models.Model):
    """
    Notification model for user activities (follows, likes, comments).
    """
    NOTIFICATION_TYPES = [
        ('follow', 'Follow'),
        ('like', 'Like'),
        ('comment', 'Comment'),
        ('show_reminder', 'Show Reminder'),
        ('show_cancelled', 'Show Cancelled'),
        ('guest_request', 'Guest Request'),
        ('guest_accepted', 'Guest Accepted'),
        ('guest_declined', 'Guest Declined'),
        ('co_host_added', 'Co-Host Added'),
    ]
    
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text="User receiving the notification"
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='actions',
        help_text="User who performed the action"
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES
    )
    
    # Generic foreign key for the target object (optional)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.actor.username} {self.notification_type} → {self.recipient.username}"


class RTMPDestination(models.Model):
    """
    RTMP streaming destination for a creator.
    Stores stream keys and RTMP URLs for platforms like YouTube, Twitch, X, etc.
    """
    PLATFORM_CHOICES = [
        ('youtube', 'YouTube'),
        ('twitch', 'Twitch'),
        ('twitter', 'X / Twitter'),
        ('kick', 'Kick'),
        ('rumble', 'Rumble'),
        ('custom', 'Custom'),
    ]

    # Default RTMP URLs per platform
    DEFAULT_RTMP_URLS = {
        'youtube': 'rtmp://a.rtmp.youtube.com/live2',
        'twitch': 'rtmp://live.twitch.tv/app',
        'twitter': 'rtmps://va.pscp.tv:443/x',
        'kick': 'rtmps://fa723fc1b171.global-contribute.live-video.net/app',
        'rumble': 'rtmp://live.rumble.com/live',
        'custom': '',
    }

    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='rtmp_destinations'
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    stream_key = models.CharField(max_length=500, help_text="Stream key (kept server-side)")
    rtmp_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="RTMP ingest URL (auto-filled per platform, editable for custom)"
    )
    label = models.CharField(max_length=100, blank=True, help_text="Friendly label, e.g. 'My YouTube Channel'")
    is_active = models.BooleanField(default=True, help_text="Whether this destination is currently enabled")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_active', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

    def save(self, *args, **kwargs):
        # Auto-fill RTMP URL from platform defaults if not set
        if not self.rtmp_url and self.platform in self.DEFAULT_RTMP_URLS:
            self.rtmp_url = self.DEFAULT_RTMP_URLS[self.platform]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} — {self.get_platform_display()} ({self.label or 'No label'})"


class Subscription(models.Model):
    """
    Creator subscription plan — determines access to playout features.
    """
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('starter', 'Starter'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('trial', 'Trial'),
    ]

    user = models.OneToOneField(
        'User',
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    stx_address = models.CharField(
        max_length=100, blank=True,
        help_text="Stacks address used for payment"
    )
    stx_tx_id = models.CharField(
        max_length=100, blank=True,
        help_text="Last payment transaction ID"
    )

    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
        ]

    @property
    def is_active(self):
        if self.status != 'active':
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True

    @property
    def plan_display(self):
        return self.get_plan_display()

    def __str__(self):
        return f"{self.user.username} — {self.get_plan_display()} ({self.status})"


class CreatorPlaylist(models.Model):
    """
    Maps DCPE playlist names to specific creators for access control.
    Admins assign playlists to creators; creators only see their own.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='creator_playlists'
    )
    dcpe_playlist_name = models.CharField(
        max_length=255, db_index=True,
        help_text="Exact playlist name as it appears in DCPE"
    )
    label = models.CharField(
        max_length=255, blank=True,
        help_text="Friendly display name (optional, shows DCPE name if empty)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'dcpe_playlist_name']
        ordering = ['dcpe_playlist_name']

    def __str__(self):
        return f"{self.user.username} → {self.dcpe_playlist_name}"


class DappPointEvent(models.Model):
    """
    Audit log of DAPP point awards for a user.
    Points are credited on every verified x402 payment.
    """
    ACTION_CHOICES = [
        ('tip_sent', 'Tip Sent'),
        ('tip_received', 'Tip Received'),
        ('subscription_upgrade', 'Subscription Upgrade'),
        ('merch_purchase', 'Merch Purchase'),
        ('wallet_signup', 'Wallet Signup Bonus'),
    ]
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='point_events'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    points = models.IntegerField()
    tx_id = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]

    def __str__(self):
        return f"{self.user.username} +{self.points}pts ({self.action})"
