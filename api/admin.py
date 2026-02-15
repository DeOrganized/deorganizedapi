from django.contrib import admin
from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    """Admin interface for Feedback submissions"""
    list_display = ['category', 'user_identifier', 'created_at', 'resolved']
    list_filter = ['category', 'resolved', 'created_at']
    search_fields = ['message', 'user_identifier', 'admin_notes']
    readonly_fields = ['category', 'message', 'user_identifier', 'created_at']
    fields = ['category', 'user_identifier', 'message', 'created_at', 'resolved', 'admin_notes']
    ordering = ['-created_at']
    
    def has_add_permission(self, request):
        """Prevent adding feedback from admin (only through API)"""
        return False

