from django.db import migrations
from django.utils.text import slugify


def create_communities_for_creators(apps, schema_editor):
    User = apps.get_model('users', 'User')
    Community = apps.get_model('communities', 'Community')
    Membership = apps.get_model('communities', 'Membership')
    Post = apps.get_model('posts', 'Post')
    Show = apps.get_model('shows', 'Show')
    Event = apps.get_model('events', 'Event')
    Merch = apps.get_model('merch', 'Merch')

    for user in User.objects.filter(role='creator'):
        base_slug = slugify(user.username) or slugify(user.display_name or '') or f'community-{user.pk}'
        slug = base_slug
        counter = 1
        while Community.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        community = Community.objects.create(
            name=user.display_name or user.username,
            slug=slug,
            description=user.bio or '',
            created_by=user,
            tier='free',
        )

        Membership.objects.create(
            user=user,
            community=community,
            role='founder',
        )

        Post.objects.filter(author=user).update(community=community)
        Show.objects.filter(creator=user).update(community=community)
        Event.objects.filter(organizer=user).update(community=community)
        Merch.objects.filter(creator=user).update(community=community)


def reverse_migrate(apps, schema_editor):
    # Remove auto-created communities — leaves content with community=NULL
    Community = apps.get_model('communities', 'Community')
    Community.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0001_initial'),
        ('posts', '0003_post_community'),
        ('shows', '0013_show_community'),
        ('events', '0008_event_community'),
        ('merch', '0004_merch_community'),
        ('users', '0018_dapointevent_action_is_read'),
    ]

    operations = [
        migrations.RunPython(
            create_communities_for_creators,
            reverse_code=reverse_migrate,
        ),
    ]
