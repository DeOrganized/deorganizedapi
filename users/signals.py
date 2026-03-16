"""
Django signals for creating notifications on user interactions.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import Like, Comment, Notification


def get_content_owner(content_object):
    """
    Get the owner of a content object, checking common field names:
    - creator (Show)
    - author (Post)
    - organizer (Event)
    Returns the owner user or None.
    """
    for attr in ('creator', 'author', 'organizer'):
        owner = getattr(content_object, attr, None)
        if owner is not None:
            return owner
    return None


@receiver(post_save, sender=Like)
def create_like_notification(sender, instance, created, **kwargs):
    """Create notification when someone likes content"""
    if created:
        try:
            # Instance is the Like object
            content_object = instance.content_object
            if not content_object:
                print(f"DEBUG: No content_object found for Like ID {instance.id}")
                return

            recipient = get_content_owner(content_object)
            
            # Don't notify if liking own content
            if recipient and recipient != instance.user:
                Notification.objects.create(
                    recipient=recipient,
                    actor=instance.user,
                    notification_type='like',
                    content_type=instance.content_type,
                    object_id=instance.object_id
                )
        except Exception as e:
            # Log error but don't crash the request
            print(f"Error creating like notification: {str(e)}")


@receiver(post_save, sender=Comment)
def create_comment_notification(sender, instance, created, **kwargs):
    """Create notification when someone comments on content or replies to a comment"""
    if created:
        try:
            # 1. Handle notification for replies
            if instance.parent:
                if instance.parent.user != instance.user:
                    Notification.objects.create(
                        recipient=instance.parent.user,
                        actor=instance.user,
                        notification_type='comment_reply',
                        content_type=instance.content_type,
                        object_id=instance.object_id
                    )
                return

            # 2. Handle notification for top-level comments
            content_object = instance.content_object
            if not content_object:
                print(f"DEBUG: No content_object found for Comment ID {instance.id}")
                return

            recipient = get_content_owner(content_object)
            
            # Don't notify if commenting on own content
            if recipient and recipient != instance.user:
                Notification.objects.create(
                    recipient=recipient,
                    actor=instance.user,
                    notification_type='comment',
                    content_type=instance.content_type,
                    object_id=instance.object_id
                )
        except Exception as e:
            # Log error but don't crash the request
            print(f"Error creating comment notification: {str(e)}")


# ---------------------------------------------------------------------------
# Auto-create Subscription for every new user
# ---------------------------------------------------------------------------

@receiver(post_save, sender='users.User')
def create_user_subscription(sender, instance, created, **kwargs):
    """Auto-create a free Subscription when a new user is created."""
    if created:
        from .models import Subscription
        Subscription.objects.get_or_create(
            user=instance,
            defaults={'plan': 'free', 'status': 'active'}
        )


# ---------------------------------------------------------------------------
# Auto-create CreatorPlaylist when subscription upgrades to a paid plan
# ---------------------------------------------------------------------------

@receiver(post_save, sender='users.Subscription')
def provision_creator_playlist(sender, instance, created, **kwargs):
    """
    Auto-create a CreatorPlaylist row when a subscription becomes paid/active.
    This ensures the DCPE playlist ownership check passes for uploads and
    playlist selection once DCPE's create-folder endpoint is live.
    """
    paid_plans = ('starter', 'pro', 'enterprise')
    if instance.plan in paid_plans and instance.is_active:
        from .models import CreatorPlaylist
        folder_name = f"creator_{instance.user_id}_{instance.user.username}"
        CreatorPlaylist.objects.get_or_create(
            user=instance.user,
            defaults={'dcpe_playlist_name': folder_name},
        )
