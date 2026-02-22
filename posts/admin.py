from django.contrib import admin
from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ['author', 'content_preview', 'is_pinned', 'created_at']
    list_filter = ['is_pinned', 'created_at']
    search_fields = ['author__username', 'content']
    date_hierarchy = 'created_at'
    raw_id_fields = ['author']

    def content_preview(self, obj):
        return obj.content[:80] + '...' if len(obj.content) > 80 else obj.content
    content_preview.short_description = 'Content'
