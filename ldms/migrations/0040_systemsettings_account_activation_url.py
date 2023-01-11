# Generated by Django 3.2 on 2020-11-21 19:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0039_auto_20201120_1638'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='account_activation_url',
            field=models.CharField(default='http://0.0.0.0:8080/#/dashboard/activate/', help_text='Url sent to user to activate his account. Uid and token will be appended to the url', max_length=255),
        ),
    ]