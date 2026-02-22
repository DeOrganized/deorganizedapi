from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation


class Post(models.Model):
    """
    Community post model for the feed system.
    Creators can publish text posts with optional images.
    Reuses the existing Like/Comment system via GenericRelation.
    """
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='posts'
    )
    content = models.TextField(max_length=2000)
    image = models.ImageField(upload_to='posts/', blank=True, null=True)
    is_pinned = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Engagement via generic relations (reuses existing Like/Comment system)
    likes = GenericRelation('users.Like', related_query_name='post')
    comments = GenericRelation('users.Comment', related_query_name='post')

    class Meta:
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['author', '-created_at']),
        ]

    def __str__(self):
        return f"{self.author.username}: {self.content[:50]}"

    @property
    def like_count(self):
        return self.likes.count()

    @property
    def comment_count(self):
        return self.comments.count()
