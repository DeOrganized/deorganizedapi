from django.db import migrations


def clear_signing_address(apps, schema_editor):
    User = apps.get_model('users', 'User')
    updated = User.objects.exclude(signing_address=None).update(signing_address=None)
    print(f"[0017] Cleared signing_address on {updated} user(s)")


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0016_user_signing_address'),
    ]

    operations = [
        migrations.RunPython(clear_signing_address, migrations.RunPython.noop),
    ]
