# Generated by Django 3.2 on 2020-12-06 13:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0051_scheduledtask_orig_args'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='enable_caching',
            field=models.BooleanField(default=True, help_text='If enabled, results of computation will be cached for a period as specified by the cache limit field', null=True),
        ),
    ]