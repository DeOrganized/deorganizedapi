from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


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
