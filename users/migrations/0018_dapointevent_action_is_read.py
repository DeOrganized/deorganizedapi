from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0017_clear_signing_address'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dapppointevent',
            name='action',
            field=models.CharField(max_length=64),
        ),
        migrations.AddField(
            model_name='dapppointevent',
            name='is_read',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
