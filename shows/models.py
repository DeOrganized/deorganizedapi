from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.utils.text import slugify
from django.utils import timezone
from datetime import datetime, timedelta, date, time
import pytz


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
    
    # Guest creators appearing on this show
    guests = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='guest_on_shows',
        blank=True,
        limit_choices_to={'role': 'creator'},
        help_text="Creators appearing as guests on this show"
    )
    
    # Co-hosts for this show (show appears on their profile/dashboard)
    co_hosts = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='co_hosted_shows',
        blank=True,
        help_text="Co-hosts who share this show on their profile"
    )
    
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
    
    # REMOVED: like_count and comment_count properties
    # These were conflicting with queryset annotations in views
    # Counts are now calculated exclusively via annotations in ShowViewSet
    
    def get_schedule_display(self):
        """Return human-readable schedule"""
        if not self.is_recurring or not self.scheduled_time:
            return "No recurring schedule"
        
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

    def should_air_on_date(self, date_obj):
        """
        Check if the show should air on a given date based on recurrence pattern.
        """
        if not self.is_recurring:
            return False
            
        # Check if this date is specifically cancelled
        if date_obj.isoformat() in self.cancelled_instances:
            return False
            
        weekday = date_obj.weekday()  # 0=Monday, 6=Sunday
        
        if self.recurrence_type == 'SPECIFIC_DAY':
            return weekday == self.day_of_week
        elif self.recurrence_type == 'DAILY':
            return True
        elif self.recurrence_type == 'WEEKDAYS':
            return weekday <= 4  # Mon-Fri
        elif self.recurrence_type == 'WEEKENDS':
            return weekday >= 5  # Sat-Sun
        return False

    def get_upcoming_occurrences(self, count=5, from_datetime=None):
        """
        Returns a list of the next N scheduled datetimes for this show.
        """
        if not self.is_recurring or not self.scheduled_time:
            return []
            
        if from_datetime is None:
            from_datetime = timezone.now()
            
        if timezone.is_naive(from_datetime):
            from_datetime = timezone.make_aware(from_datetime)

        occurrences = []
        check_date = from_datetime.date()
        
        # Start checking from today if time hasn't passed, else tomorrow
        if from_datetime.time() >= self.scheduled_time:
            check_date += timedelta(days=1)
            
        # Look ahead up to 90 days to find count occurrences
        lookahead_days = 0
        while len(occurrences) < count and lookahead_days < 90:
            if self.should_air_on_date(check_date):
                dt = timezone.make_aware(datetime.combine(check_date, self.scheduled_time))
                occurrences.append(dt)
            check_date += timedelta(days=1)
            lookahead_days += 1
            
        return occurrences
    
    def get_next_occurrence(self, from_datetime=None):
        """
        Calculates the next occurrence of this show from the given datetime.
        If from_datetime is None, use current time.
        """
        if not self.is_recurring or not self.scheduled_time:
            return None
            
        if from_datetime is None:
            from_datetime = timezone.now()
            
        # Ensure we are working with a timezone-aware datetime
        if timezone.is_naive(from_datetime):
            from_datetime = timezone.make_aware(from_datetime)
            
        # Get the day of week (0=Monday, 6=Sunday)
        current_day = from_datetime.weekday()
        current_time = from_datetime.time()
        
        # Helper to get next date for a specific day of week
        def get_next_weekday_date(start_date, target_weekday):
            days_ahead = target_weekday - start_date.weekday()
            if days_ahead <= 0: # Target day is today or earlier in the week
                days_ahead += 7
            return start_date + timedelta(days_ahead)

        candidates = []
        
        if self.recurrence_type == 'SPECIFIC_DAY' and self.day_of_week is not None:
            # Check if it's today and time hasn't passed
            if current_day == self.day_of_week and current_time < self.scheduled_time:
                candidates.append(from_datetime.date())
            else:
                candidates.append(get_next_weekday_date(from_datetime.date(), self.day_of_week))
                
        elif self.recurrence_type == 'DAILY':
            if current_time < self.scheduled_time:
                candidates.append(from_datetime.date())
            else:
                candidates.append(from_datetime.date() + timedelta(days=1))
                
        elif self.recurrence_type == 'WEEKDAYS':
            # Mon-Fri (0-4)
            if current_day <= 4:
                if current_time < self.scheduled_time:
                    candidates.append(from_datetime.date())
                else:
                    # Next weekday
                    next_day = 0 if current_day == 4 else current_day + 1
                    candidates.append(get_next_weekday_date(from_datetime.date(), next_day))
            else:
                # Sat/Sun -> Monday
                candidates.append(get_next_weekday_date(from_datetime.date(), 0))
                
        elif self.recurrence_type == 'WEEKENDS':
            # Sat-Sun (5-6)
            if current_day >= 5:
                if current_time < self.scheduled_time:
                    candidates.append(from_datetime.date())
                else:
                    next_day = 5 if current_day == 6 else 6
                    candidates.append(get_next_weekday_date(from_datetime.date(), next_day))
            else:
                # Mon-Fri -> Saturday
                candidates.append(get_next_weekday_date(from_datetime.date(), 5))

        if not candidates:
            return None
            
        next_date = min(candidates)
        # Check if this date is cancelled
        if next_date.isoformat() in self.cancelled_instances:
            # Recursively find the next one
            return self.get_next_occurrence(
                timezone.make_aware(datetime.combine(next_date + timedelta(days=1), time.min))
            )
            
        return timezone.make_aware(datetime.combine(next_date, self.scheduled_time))
    
    def save(self, *args, **kwargs):
        """Auto-generate slug from title if not set"""
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            
            # Ensure unique slug
            while Show.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            self.slug = slug
        
        super().save(*args, **kwargs)


class ShowEpisode(models.Model):
    """
    Model representing individual episodes of a show.
    Used for archived episodes or to track past broadcasts.
    """
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name='episodes')
    episode_number = models.IntegerField(help_text="Episode number for this show")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    air_date = models.DateField(help_text="Date this episode aired")
    duration = models.DurationField(blank=True, null=True, help_text="Duration of the episode")
    video_url = models.URLField(blank=True, help_text="URL to recorded episode (YouTube, etc.)")
    
    # Premium Gating
    is_premium = models.BooleanField(default=False)
    price_stx = models.BigIntegerField(default=0, help_text="Price in microSTX")
    price_usdcx = models.BigIntegerField(default=0, help_text="Price in smallest USDCx unit")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-air_date','-episode_number']
        unique_together = ['show', 'episode_number']
        indexes = [
            models.Index(fields=['show', '-air_date']),
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


class GuestRequest(models.Model):
    """
    Model for managing guest appearance requests on shows.
    Creators can request to appear as guests on other creators' shows.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]
    
    show = models.ForeignKey(
        Show,
        on_delete=models.CASCADE,
        related_name='guest_requests',
        help_text="Show that the guest request is for"
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_guest_requests',
        limit_choices_to={'role': 'creator'},
        help_text="Creator requesting to be a guest"
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )
    message = models.TextField(
        blank=True,
        max_length=500,
        help_text="Optional message from the requester"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['show', 'requester']  # Prevent duplicate requests
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['show', 'status']),
            models.Index(fields=['requester', 'status']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.requester.username} → {self.show.title} ({self.status})"
