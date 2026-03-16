from django.contrib import admin
from .models import PaymentReceipt

@admin.register(PaymentReceipt)
class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource_type', 'resource_id', 'token_type', 'amount', 'paid_at')
    list_filter = ('resource_type', 'token_type')
    search_fields = ('user__username', 'tx_id', 'resource_id')
    readonly_fields = ('paid_at',)
