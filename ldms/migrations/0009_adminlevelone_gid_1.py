# Generated by Django 3.2 on 2020-09-03 09:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0008_auto_20200903_0848'),
    ]

    operations = [
        migrations.AddField(
            model_name='adminlevelone',
            name='gid_1',
            field=models.CharField(default='', max_length=50),
            preserve_default=False,
        ),
    ]
