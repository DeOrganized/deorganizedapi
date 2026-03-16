from django.contrib import admin
from .models import Merch, Order

@admin.register(Merch)
class MerchAdmin(admin.ModelAdmin):
    list_display = ('name', 'creator', 'price_stx', 'is_active', 'created_at')
    list_filter = ('is_active', 'creator')
    search_fields = ('name', 'description', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'merch', 'amount_paid', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('tx_id', 'user__username', 'merch__name')
