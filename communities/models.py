from django.db import models
from django.conf import settings
from django.utils.text import slugify


class Community(models.Model):
    TIER_CHOICES = [
        ('free', 'Free'),
        ('creator', 'Creator'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(max_length=2000, blank=True)
    avatar = models.ImageField(upload_to='community_avatars/', null=True, blank=True)
    banner = models.ImageField(upload_to='community_banners/', null=True, blank=True)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='free')

    # Creator/owner reference — also held as Membership(role='founder')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_communities'
    )

    # Optional agent linkage (agent_id deferred to future phase)
    agent_api_url = models.URLField(blank=True, null=True)

    # Socials
    website = models.URLField(blank=True, null=True)
    twitter = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'communities'
        indexes = [
            models.Index(fields=['tier', '-created_at']),
            models.Index(fields=['slug']),
        ]

    @property
    def member_count(self):
        return self.memberships.count()

    @property
    def founder(self):
        membership = self.memberships.filter(role='founder').first()
        return membership.user if membership else self.created_by

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Community.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Membership(models.Model):
    ROLE_CHOICES = [
        ('founder', 'Founder'),
        ('admin', 'Admin'),
        ('moderator', 'Moderator'),
        ('member', 'Member'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'community')
        ordering = ['role', 'joined_at']
        indexes = [
            models.Index(fields=['user', 'community']),
            models.Index(fields=['community', 'role']),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.community.name} ({self.role})"


class CommunityFollow(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='community_follows'
    )
    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name='followers'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'community')

    def __str__(self):
        return f"{self.user.username} follows {self.community.name}"
