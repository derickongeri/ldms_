# Generated by Django 3.2 on 2020-11-23 11:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0040_systemsettings_account_activation_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='change_password_url',
            field=models.CharField(default='http://0.0.0.0:8080/#/dashboard/forgotpassword/', help_text='Url sent to user to reset his password. Uid and token will be appended to the url', max_length=255),
        ),
    ]
