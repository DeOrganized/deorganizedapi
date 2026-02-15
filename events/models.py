from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.utils import timezone


class Event(models.Model):
    """
    Model representing events with scheduling, location, and registration support.
    """
    title = models.CharField(max_length=255)
    description = models.TextField()
    banner_image = models.ImageField(
        upload_to='events/banners/',
        blank=True,
        null=True
    )
    
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organized_events'
    )
    
    # Scheduling
    start_datetime = models.DateTimeField(blank=True, null=True, help_text="Required for one-off events, optional for recurring")
    end_datetime = models.DateTimeField(blank=True, null=True, help_text="Required for one-off events, optional for recurring")
    
    # Location
    venue_name = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    is_virtual = models.BooleanField(default=False)
    meeting_link = models.URLField(blank=True, help_text="Link for virtual events")
    
    # Registration
    capacity = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Maximum number of attendees (leave blank for unlimited)"
    )
    registration_link = models.URLField(blank=True)
    registration_deadline = models.DateTimeField(blank=True, null=True)
    
    # Privacy
    is_public = models.BooleanField(default=True)
    
    # Recurrence choices (same as Show)
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
        help_text="Day of the week for SPECIFIC_DAY recurring events (0=Monday, 6=Sunday)"
    )
    scheduled_time = models.TimeField(
        blank=True,
        null=True,
        help_text="Time of day for the recurring event"
    )
    
    # Track cancelled instances for recurring events
    cancelled_instances = models.JSONField(
        default=list,
        blank=True,
        help_text="List of ISO date strings for cancelled recurring event instances"
    )
    
    # Analytics
    share_count = models.IntegerField(default=0, help_text="Number of times this event has been shared")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Generic relations for likes and comments
    likes = GenericRelation('users.Like', related_query_name='event')
    comments = GenericRelation('users.Comment', related_query_name='event')
    
    class Meta:
        ordering = ['start_datetime']
        indexes = [
            models.Index(fields=['start_datetime', 'is_public']),
            models.Index(fields=['organizer', '-start_datetime']),
        ]
    
    def __str__(self):
        if self.start_datetime:
            return f"{self.title} - {self.start_datetime.strftime('%Y-%m-%d')}"
        return f"{self.title} (recurring)"
    
    @property
    def like_count(self):
        return self.likes.count()
    
    @property
    def comment_count(self):
        return self.comments.count()
    
    @property
    def is_upcoming(self):
        """Check if event is in the future"""
        if not self.start_datetime:
            return self.is_recurring  # recurring events are always "upcoming"
        return self.start_datetime > timezone.now()
    
    @property
    def is_ongoing(self):
        """Check if event is currently happening"""
        if not self.start_datetime or not self.end_datetime:
            return False
        now = timezone.now()
        return self.start_datetime <= now <= self.end_datetime
    
    @property
    def is_past(self):
        """Check if event has ended"""
        if not self.end_datetime:
            return False
        return self.end_datetime < timezone.now()
    
    @property
    def status(self):
        """Return current event status"""
        if self.is_recurring and not self.start_datetime:
            return "upcoming"
        if self.is_ongoing:
            return "ongoing"
        elif self.is_upcoming:
            return "upcoming"
        else:
            return "past"
    
    def get_schedule_display(self):
        """Return human-readable schedule"""
        if not self.is_recurring or not self.scheduled_time:
            return "One-time event"
        
        time_str = self.scheduled_time.strftime('%I:%M %p')
        
        if self.recurrence_type == 'SPECIFIC_DAY':
            day_name = dict(self.DAY_OF_WEEK_CHOICES)[self.day_of_week]
            return f"Every {day_name} at {time_str}"
        elif self.recurrence_type == 'DAILY':
            return f"Daily at {time_str}"
        elif self.recurrence_type == 'WEEKDAYS':
            return f"Weekdays (Mon-Fri) at {time_str}"
        elif self.recurrence_type == 'WEEKENDS':
            return f"Weekends (Sat-Sun) at {time_str}"
        else:
            return "Custom schedule"
