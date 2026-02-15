from django.db import models

# Create your models here.

class Feedback(models.Model):
    """Model to store user feedback submissions"""
    CATEGORY_CHOICES = [
        ('bug', 'Bug Report'),
        ('feature', 'Feature Request'),
        ('general', 'General Feedback'),
    ]
    
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    message = models.TextField()
    user_identifier = models.CharField(max_length=255, help_text="Email, username, or 'anonymous'")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    admin_notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Feedback'
        verbose_name_plural = 'Feedback Submissions'
    
    def __str__(self):
        return f"{self.category.title()} - {self.user_identifier} - {self.created_at.strftime('%Y-%m-%d')}"

