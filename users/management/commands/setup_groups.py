"""
Management command to create the default permission groups.

Usage:
    python manage.py setup_groups

Creates:
  - production_staff (playout engine access)
  - platform_admin (full admin access)
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = 'Create default permission groups: production_staff, platform_admin'

    def handle(self, *args, **options):
        # ---------------------------------------------------------------
        # 1. production_staff — can control the playout engine
        # ---------------------------------------------------------------
        prod_group, created = Group.objects.get_or_create(name='production_staff')
        if created:
            self.stdout.write(self.style.SUCCESS('Created group: production_staff'))
        else:
            self.stdout.write('Group production_staff already exists')

        # Give production_staff all permissions on RTMPDestination and Subscription
        for model_name in ['rtmpdestination', 'subscription']:
            try:
                ct = ContentType.objects.get(app_label='users', model=model_name)
                perms = Permission.objects.filter(content_type=ct)
                prod_group.permissions.add(*perms)
            except ContentType.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f'  ContentType users.{model_name} not found — run migrations first'
                ))

        # ---------------------------------------------------------------
        # 2. platform_admin — full platform administration
        # ---------------------------------------------------------------
        admin_group, created = Group.objects.get_or_create(name='platform_admin')
        if created:
            self.stdout.write(self.style.SUCCESS('Created group: platform_admin'))
        else:
            self.stdout.write('Group platform_admin already exists')

        # Give platform_admin all Users app permissions
        users_cts = ContentType.objects.filter(app_label='users')
        all_perms = Permission.objects.filter(content_type__in=users_cts)
        admin_group.permissions.add(*all_perms)

        # Also give permissions on shows, news, events
        for app in ['shows', 'news', 'events', 'posts']:
            app_cts = ContentType.objects.filter(app_label=app)
            if app_cts.exists():
                app_perms = Permission.objects.filter(content_type__in=app_cts)
                admin_group.permissions.add(*app_perms)

        self.stdout.write(self.style.SUCCESS('Done — permission groups are ready.'))
        self.stdout.write('')
        self.stdout.write('To assign a user to a group:')
        self.stdout.write('  Django Admin → Users → [user] → Groups → add production_staff or platform_admin')
        self.stdout.write('  Or via shell:')
        self.stdout.write('    from django.contrib.auth.models import Group')
        self.stdout.write('    Group.objects.get(name="production_staff").user_set.add(user)')
