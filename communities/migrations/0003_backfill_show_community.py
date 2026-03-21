"""
Idempotent backfill: assign community to shows/events/merch where community is still NULL.

Safe to run multiple times — only touches records where community_id IS NULL.
This covers cases where:
  - communities.0002 ran but shows were created afterwards
  - communities.0002 was skipped or partially applied in production
"""
from django.db import migrations


def backfill_show_community(apps, schema_editor):
    Membership = apps.get_model('communities', 'Membership')
    Show = apps.get_model('shows', 'Show')
    Event = apps.get_model('events', 'Event')
    Merch = apps.get_model('merch', 'Merch')

    founders = (
        Membership.objects
        .filter(role='founder')
        .select_related('user', 'community')
    )

    for m in founders:
        shows_updated = Show.objects.filter(creator=m.user, community__isnull=True).update(community=m.community)
        events_updated = Event.objects.filter(organizer=m.user, community__isnull=True).update(community=m.community)
        merch_updated = Merch.objects.filter(creator=m.user, community__isnull=True).update(community=m.community)
        if any([shows_updated, events_updated, merch_updated]):
            print(
                f"  {m.user.username} → {m.community.slug}: "
                f"{shows_updated} shows, {events_updated} events, {merch_updated} merch"
            )


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0002_migrate_creators'),
        ('shows', '0013_show_community'),
        ('events', '0008_event_community'),
        ('merch', '0004_merch_community'),
    ]

    operations = [
        migrations.RunPython(
            backfill_show_community,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
