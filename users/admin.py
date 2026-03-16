from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Like, Comment, Follow, Subscription, RTMPDestination, Notification, CreatorPlaylist


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for User model"""
    list_display = ['username', 'email', 'role', 'is_verified', 'is_staff', 'date_joined']
    list_filter = ['role', 'is_verified', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    readonly_fields = ['date_joined', 'last_login']
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'display_name')}),
        ('Role & Profile', {
            'fields': ('role', 'bio', 'profile_picture', 'cover_photo', 'is_verified', 'stacks_address')
        }),
        ('Social Links', {
            'fields': ('website', 'twitter', 'instagram', 'youtube')
        }),
        ('Broadcast Schedule', {
            'fields': ('broadcast_time', 'broadcast_days', 'broadcast_timezone'),
            'classes': ('collapse',),
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Role & Profile', {
            'fields': ('role',)
        }),
    )


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    """Admin for Like model"""
    list_display = ['user', 'content_type', 'object_id', 'created_at']
    list_filter = ['content_type', 'created_at']
    search_fields = ['user__username']
    date_hierarchy = 'created_at'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    """Admin for Comment model"""
    list_display = ['user', 'text_preview', 'content_type', 'object_id', 'parent', 'created_at']
    list_filter = ['content_type', 'created_at']
    search_fields = ['user__username', 'text']
    date_hierarchy = 'created_at'
    
    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Comment'


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    """Admin for Follow model"""
    list_display = ['follower', 'following', 'created_at']
    search_fields = ['follower__username', 'following__username']
    date_hierarchy = 'created_at'


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin for Subscription model"""
    list_display = ['user', 'plan', 'status', 'is_active', 'started_at', 'expires_at']
    list_filter = ['plan', 'status']
    search_fields = ['user__username']
    list_editable = ['plan', 'status']
    date_hierarchy = 'started_at'


@admin.register(RTMPDestination)
class RTMPDestinationAdmin(admin.ModelAdmin):
    """Admin for RTMP Destination model"""
    list_display = ['user', 'platform', 'label', 'is_active', 'created_at']
    list_filter = ['platform', 'is_active']
    search_fields = ['user__username', 'label']
    list_editable = ['is_active']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin for Notification model"""
    list_display = ['recipient', 'actor', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']
    search_fields = ['recipient__username', 'actor__username']
    date_hierarchy = 'created_at'


@admin.register(CreatorPlaylist)
class CreatorPlaylistAdmin(admin.ModelAdmin):
    """Admin for CreatorPlaylist — assign DCPE playlists to creators"""
    list_display = ['user', 'dcpe_playlist_name', 'label', 'created_at']
    list_filter = ['user']
    search_fields = ['user__username', 'dcpe_playlist_name', 'label']
    raw_id_fields = ['user']
