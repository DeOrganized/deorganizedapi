from django.db import models
from django.conf import settings

class Thread(models.Model):
    """
    Represents a conversation between two or more users.
    """
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='threads')
    is_premium = models.BooleanField(default=False)
    price_stx = models.BigIntegerField(default=0)  # microSTX
    price_usdcx = models.BigIntegerField(default=0) # smallest USDCx unit
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        participant_names = ", ".join([u.username for u in self.participants.all()[:3]])
        return f"Thread ({participant_names})"

class Message(models.Model):
    """
    Individual message within a thread.
    """
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    text = models.TextField()
    is_read = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Message from {self.sender.username} in {self.thread}"
