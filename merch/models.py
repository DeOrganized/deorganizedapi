from django.db import models
from django.conf import settings
from django.utils.text import slugify

class Merch(models.Model):
    """
    Model representing physical or digital merchandise sold by creators.
    """
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='merch_items',
        limit_choices_to={'role': 'creator'}
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=300, unique=True, blank=True)
    description = models.TextField()
    price_stx = models.DecimalField(max_digits=20, decimal_places=6, help_text="Price in STX (microstacks)")
    price_usdcx = models.DecimalField(max_digits=20, decimal_places=6, help_text="Price in USDCx")
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='merch/images/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Merch"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} by {self.creator.username}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            # Ensure uniqueness
            base_slug = self.slug
            count = 1
            while Merch.objects.filter(slug=self.slug).exists():
                self.slug = f"{base_slug}-{count}"
                count += 1
        super().save(*args, **kwargs)

class Order(models.Model):
    """
    Tracks purchases of merch items, verified via x402 payment tx.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Transfer'),
        ('paid', 'Paid/Verified'),
        ('shipped', 'Shipped'),
        ('completed', 'Completed'),
        ('failed', 'Failed/Refunded'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='merch_orders'
    )
    merch = models.ForeignKey(Merch, on_delete=models.CASCADE, related_name='orders')
    quantity = models.PositiveIntegerField(default=1)
    
    # Payment details (x402) — filled after payment completes
    tx_id = models.CharField(max_length=255, blank=True, default='', help_text="Stacks transaction ID")
    payment_currency = models.CharField(max_length=10, choices=[('STX', 'STX'), ('USDCx', 'USDCx'), ('sBTC', 'sBTC')], blank=True, default='')
    amount_paid = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Shipping info (optional/placeholder)
    shipping_address = models.TextField(blank=True)
    buyer_note = models.TextField(blank=True, help_text="Optional message from buyer to creator")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id} - {self.user.username} - {self.merch.name}"
