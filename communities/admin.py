from django.contrib import admin
from .models import Community, Membership, CommunityFollow


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'tier', 'created_by', 'created_at']
    search_fields = ['name', 'slug']
    list_filter = ['tier']
    readonly_fields = ['slug', 'created_at', 'updated_at']


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'community', 'role', 'joined_at']
    list_filter = ['role']
    search_fields = ['user__username', 'community__name']


@admin.register(CommunityFollow)
class CommunityFollowAdmin(admin.ModelAdmin):
    list_display = ['user', 'community', 'created_at']
    search_fields = ['user__username', 'community__name']
