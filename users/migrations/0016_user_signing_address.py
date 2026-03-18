from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0015_add_dapp_points'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='signing_address',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Address recovered from the signing key (stx_signMessage). May differ from stacks_address.',
                max_length=64,
                null=True,
            ),
        ),
    ]
