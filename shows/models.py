from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.utils.text import slugify


class Tag(models.Model):
    """
    Tags for categorizing shows
    """
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Show(models.Model):
    """
    Model representing a show that can be recurring or one-time.
    Supports thumbnail images and scheduling.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    DAY_OF_WEEK_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    RECURRENCE_CHOICES = [
        ('SPECIFIC_DAY', 'Specific Day'),
        ('DAILY', 'Daily'),
        ('WEEKDAYS', 'Weekdays (Mon-Fri)'),
        ('WEEKENDS', 'Weekends (Sat-Sun)'),
    ]
    
    PLATFORM_CHOICES = [
        ('youtube', 'YouTube'),
        ('twitter', 'Twitter/X'),
        ('twitch', 'Twitch'),
        ('rumble', 'Rumble'),
        ('kick', 'Kick'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=300, unique=True, blank=True)
    description = models.TextField()
    thumbnail = models.ImageField(upload_to='shows/thumbnails/', blank=True, null=True)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shows',
        limit_choices_to={'role': 'creator'}
    )
    
    # Tags for categorization
    tags = models.ManyToManyField(Tag, related_name='shows', blank=True)
    
    # External links (Watch Now functionality)
    external_link = models.URLField(
        blank=True,
        null=True,
        help_text="Link to external content (YouTube, Twitter Space, etc.)"
    )
    link_platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES,
        blank=True,
        help_text="Platform for the external link"
    )
    
    # Recurring schedule fields
    is_recurring = models.BooleanField(default=False)
    recurrence_type = models.CharField(
        max_length=20,
        choices=RECURRENCE_CHOICES,
        blank=True,
        null=True,
        help_text="Type of recurrence pattern"
    )
    day_of_week = models.IntegerField(
        choices=DAY_OF_WEEK_CHOICES,
        blank=True,
        null=True,
        help_text="Day of the week for SPECIFIC_DAY recurring shows (0=Monday, 6=Sunday)"
    )
    scheduled_time = models.TimeField(
        blank=True,
        null=True,
        help_text="Time of day for the show (e.g., 17:00 for 5pm)"
    )
    
    # Track cancelled instances for recurring shows
    cancelled_instances = models.JSONField(
        default=list,
        blank=True,
        help_text="List of ISO date strings for cancelled recurring show instances"
    )
    
    # Generic relations for engagement (likes/comments)
    likes = GenericRelation('users.Like', content_type_field='content_type', object_id_field='object_id', related_query_name='show')
    comments = GenericRelation('users.Comment', content_type_field='content_type', object_id_field='object_id', related_query_name='show')
    
    # Analytics
    share_count = models.IntegerField(default=0, help_text="Number of times this show has been shared")
    
    # Metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Generic relations for likes and comments
    likes = GenericRelation('users.Like', related_query_name='show')
    comments = GenericRelation('users.Comment', related_query_name='show')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['creator', 'status']),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def like_count(self):
        return self.likes.count()
    
    @property
    def comment_count(self):
        return self.comments.count()
    
    def get_schedule_display(self):
        """Return human-readable schedule"""
        if not self.is_recurring or not self.scheduled_time:
            return "No recurring schedule"
        
        time_str = self.scheduled_time.strftime('%I:%M %p')
        
        if self.recurrence_type == 'DAILY':
            return f"Daily at {time_str}"
        elif self.recurrence_type == 'WEEKDAYS':
            return f"Weekdays at {time_str}"
        elif self.recurrence_type == 'WEEKENDS':
            return f"Weekends at {time_str}"
        elif self.recurrence_type == 'SPECIFIC_DAY' and self.day_of_week is not None:
            day_name = dict(self.DAY_OF_WEEK_CHOICES)[self.day_of_week]
            return f"Every {day_name} at {time_str}"
        
        return "No recurring schedule"
    
    def should_air_on_date(self, date):
        """Check if show should air on given date based on recurrence pattern"""
        if not self.is_recurring:
            return False
        
        # Check if this specific date was cancelled
        date_str = date.isoformat()
        if date_str in self.cancelled_instances:
            return False
        
        if self.recurrence_type == 'DAILY':
            return True
        elif self.recurrence_type == 'WEEKDAYS':
            return date.weekday() < 5  # Mon-Fri (0-4)
        elif self.recurrence_type == 'WEEKENDS':
            return date.weekday() >= 5  # Sat-Sun (5-6)
        elif self.recurrence_type == 'SPECIFIC_DAY':
            return date.weekday() == self.day_of_week
        
        return False
    
    def save(self, *args, **kwargs):
        """Auto-generate slug from title if not provided"""
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            
            # Ensure slug is unique
            while Show.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            self.slug = slug
        
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        """Return URL for show detail page using slug"""
        return f"/shows/{self.slug}/"



class ShowEpisode(models.Model):
    """
    Optional: Individual episodes for shows
    """
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name='episodes')
    episode_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    air_date = models.DateTimeField()
    duration = models.DurationField(blank=True, null=True, help_text="Episode duration")
    video_url = models.URLField(blank=True, help_text="Link to episode video")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['show', 'episode_number']
        unique_together = ['show', 'episode_number']
        indexes = [
            models.Index(fields=['show', 'air_date']),
        ]
    
    def __str__(self):
        return f"{self.show.title} - Episode {self.episode_number}: {self.title}"




class ShowReminder(models.Model):
    """
    Tracks show reminders and creator responses
    """
    RESPONSE_CHOICES = [
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name='reminders')
    scheduled_for = models.DateTimeField(help_text="Specific datetime this show instance is scheduled for")
    reminder_sent_at = models.DateTimeField(blank=True, null=True)
    creator_response = models.CharField(
        max_length=10,
        choices=RESPONSE_CHOICES,
        default='PENDING'
    )
    responded_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['show', 'scheduled_for']
        ordering = ['scheduled_for']
        indexes = [
            models.Index(fields=['show', 'scheduled_for']),
            models.Index(fields=['creator_response', 'scheduled_for']),
        ]
    
    def __str__(self):
        return f"{self.show.title} - {self.scheduled_for.strftime('%Y-%m-%d %H:%M')} - {self.creator_response}"

