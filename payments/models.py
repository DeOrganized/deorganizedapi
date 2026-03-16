from django.db import models
from django.conf import settings

class PaymentReceipt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payment_receipts")
    resource_type = models.CharField(max_length=50)   # "post", "episode", "message_thread", "merch_order"
    resource_id = models.CharField(max_length=255)
    tx_id = models.CharField(max_length=255, unique=True)
    token_type = models.CharField(max_length=10)       # "STX" or "USDCx"
    amount = models.BigIntegerField()                  # in microSTX or smallest USDCx unit
    receipt_token = models.TextField(blank=True)       # x402 v2 receipt for repeat access
    paid_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "resource_type", "resource_id")
        ordering = ['-paid_at']

    def __str__(self):
        return f"{self.user.username} paid for {self.resource_type}:{self.resource_id} ({self.token_type})"
