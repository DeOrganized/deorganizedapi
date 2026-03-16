from celery import shared_task
from django.utils import timezone
from datetime import timedelta, datetime
from .models import Show, ShowReminder
from users.models import Notification


@shared_task
def check_upcoming_shows():
    """
    Checks for shows starting in 30 minutes and creates reminders.
    Runs every 5 minutes via Celery Beat.
    """
    now = timezone.now()
    reminder_window_start = now + timedelta(minutes=25)  # 25-35 min window
    reminder_window_end = now + timedelta(minutes=35)
    
    # Find all recurring shows that are published
    recurring_shows = Show.objects.filter(
        is_recurring=True,
        status='published'
    ).select_related('creator')
    
    for show in recurring_shows:
        if not show.scheduled_time or not show.recurrence_type:
            continue
        
        # Check each date in the next hour
        for minutes_ahead in range(25, 36, 5):  # Check 25, 30, 35 min ahead
            check_datetime = now + timedelta(minutes=minutes_ahead)
            check_date = check_datetime.date()
            
            # Check if show should air on this date using the model method
            if show.should_air_on_date(check_date):
                # Construct the scheduled datetime
                scheduled_datetime = timezone.make_aware(
                    datetime.combine(check_date, show.scheduled_time)
                )
                
                # Only create reminder if it's 30 minutes ± 5 minutes from now
                time_until_show = (scheduled_datetime - now).total_seconds() / 60
                if 25 <= time_until_show <= 35:
                    # Create or get reminder
                    reminder, created = ShowReminder.objects.get_or_create(
                        show=show,
                        scheduled_for=scheduled_datetime,
                        defaults={'reminder_sent_at': now}
                    )
                    
                    if created:
                        # Create notification for the creator
                        Notification.objects.create(
                            recipient=show.creator,
                            actor=show.creator,  # Self-notification
                            notification_type='show_reminder',
                            content_type=None,
                            object_id=None
                        )
                        print(f"Created reminder for {show.title} at {scheduled_datetime}")


@shared_task
def auto_cancel_unconfirmed_shows():
    """
    Auto-cancels shows if creator hasn't responded within 30 minutes.
    Defaults to NO - show is cancelled.
    Runs every 5 minutes.
    """
    now = timezone.now()
    
    # Find pending reminders where show time has passed
    pending_reminders = ShowReminder.objects.filter(
        creator_response='PENDING',
        scheduled_for__lte=now
    ).select_related('show', 'show__creator')
    
    for reminder in pending_reminders:
        # Auto-cancel
        reminder.creator_response = 'CANCELLED'
        reminder.responded_at = now
        reminder.save()
        
        # Add to cancelled instances
        show = reminder.show
        date_str = reminder.scheduled_for.date().isoformat()
        
        if date_str not in show.cancelled_instances:
            show.cancelled_instances.append(date_str)
            show.save(update_fields=['cancelled_instances'])
        
        # Notify creator
        Notification.objects.create(
            recipient=show.creator,
            actor=show.creator,  # Self-notification
            notification_type='show_cancelled',
            content_type=None,
            object_id=None
        )
        print(f"Auto-cancelled show {show.title} for {reminder.scheduled_for}")


@shared_task
def cleanup_old_notifications():
    """
    Clean up old read notifications after 30 days.
    Runs daily.
    """
    cutoff_date = timezone.now() - timedelta(days=30)
    deleted_count = Notification.objects.filter(
        is_read=True,
        created_at__lt=cutoff_date
    ).delete()[0]
    
    print(f"Cleaned up {deleted_count} old notifications")
    return deleted_count
@shared_task
def auto_create_recurring_episodes():
    """
    Daily task to ensure recurring shows have future episodes provisioned.
    Ensures at least the next 5 episodes are created.
    """
    from .models import Show, ShowEpisode
    
    recurring_shows = Show.objects.filter(is_recurring=True, status='published')
    created_count = 0
    
    for show in recurring_shows:
        # Get next 5 occurrences
        upcoming = show.get_upcoming_occurrences(count=5)
        
        for occurrence in upcoming:
            air_date = occurrence.date()
            
            # Check if episode exists
            if not ShowEpisode.objects.filter(show=show, air_date=air_date).exists():
                # Get next episode number
                last_ep = ShowEpisode.objects.filter(show=show).order_by('-episode_number').first()
                next_num = (last_ep.episode_number + 1) if last_ep else 1
                
                ShowEpisode.objects.create(
                    show=show,
                    episode_number=next_num,
                    title=f"Episode {next_num}",
                    description=f"Automated episode for {show.title}",
                    air_date=air_date,
                    is_premium=False
                )
                created_count += 1
                
    return f"Created {created_count} episodes for recurring shows."
@shared_task
def register_airing_episodes():
    """
    Checks for shows that should air RIGHT NOW and ensures an episode record exists.
    Runs every minute via Celery Beat.
    """
    from .models import Show, ShowEpisode
    
    now = timezone.now()
    current_time = now.time()
    current_date = now.date()
    
    # Standardize to 1-minute precision for matching
    target_time = current_time.replace(second=0, microsecond=0)
    
    # Find active recurring shows
    recurring_shows = Show.objects.filter(is_recurring=True, status='published')
    registered_count = 0
    
    for show in recurring_shows:
        if not show.scheduled_time:
            continue
            
        # Standardize show time to 1-minute precision
        show_time = show.scheduled_time.replace(second=0, microsecond=0)
        
        # Check if the show is scheduled for this time AND this date
        if show_time == target_time and show.should_air_on_date(current_date):
            # Check if episode already exists for this date
            if not ShowEpisode.objects.filter(show=show, air_date=current_date).exists():
                # Get next episode number
                last_ep = ShowEpisode.objects.filter(show=show).order_by('-episode_number').first()
                next_num = (last_ep.episode_number + 1) if last_ep else 1
                
                ShowEpisode.objects.create(
                    show=show,
                    episode_number=next_num,
                    title=f"Episode {next_num} - {current_date.strftime('%B %d')}",
                    description=f"Automated live episode for {show.title}",
                    air_date=current_date,
                    is_premium=False
                )
                registered_count += 1
                print(f"Registered live episode for {show.title} at {target_time}")
                
    return f"Registered {registered_count} live episodes."
