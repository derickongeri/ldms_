# Generated by Django 3.2 on 2020-12-06 07:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0049_computationthreshold'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='cache_limit',
            field=models.IntegerField(default=86400, help_text='Number of seconds that results will be cached.'),
        ),
        migrations.AlterField(
            model_name='computationthreshold',
            name='enable_signedup_user_limit',
            field=models.BooleanField(default=True, help_text='If checked, Logged in users will process polygons upto a specific polygon size'),
        ),
    ]
