# Generated by Django 3.2 on 2020-08-31 17:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0005_auto_20200831_1638'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shapefile',
            name='srs',
            field=models.CharField(blank=True, max_length=254),
        ),
    ]
