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
    """
    Create notification when someone likes content.
    Only creates notification if:
    1. This is a new like (created=True)
    2. The content object has an owner (creator/author/organizer)
    3. The liker is not the owner (don't notify self-likes)
    """
    if not created:
        return
    
    content_object = instance.content_object
    owner = get_content_owner(content_object)
    if owner is None:
        return
    
    # Don't notify if user likes their own content
    if instance.user == owner:
        return
    
    Notification.objects.create(
        recipient=owner,
        actor=instance.user,
        notification_type='like',
        content_type=instance.content_type,
        object_id=instance.object_id
    )


@receiver(post_save, sender=Comment)
def create_comment_notification(sender, instance, created, **kwargs):
    """
    Create notification when someone comments on content.
    Only creates notification if:
    1. This is a new comment (created=True)
    2. The content object has an owner (creator/author/organizer)
    3. The commenter is not the owner (don't notify self-comments)
    4. This is a top-level comment (not a reply)
    """
    if not created:
        return
    
    content_object = instance.content_object
    owner = get_content_owner(content_object)
    if owner is None:
        return
    
    # Don't notify if user comments on their own content
    if instance.user == owner:
        return
    
    # Only notify on top-level comments (not replies)
    if instance.parent is not None:
        return
    
    Notification.objects.create(
        recipient=owner,
        actor=instance.user,
        notification_type='comment',
        content_type=instance.content_type,
        object_id=instance.object_id
    )

