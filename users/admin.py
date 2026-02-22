from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Like, Comment, Follow


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

