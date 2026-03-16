from django.contrib import admin
from .models import Thread, Message

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ('id', 'is_premium', 'price_stx', 'price_usdcx', 'created_at', 'updated_at')
    list_filter = ('is_premium', 'created_at', 'updated_at')
    search_fields = ('id',)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'thread', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('id', 'sender__username', 'thread__id')