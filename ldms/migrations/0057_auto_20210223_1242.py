# Generated by Django 3.1 on 2021-02-23 12:42

import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0056_auto_20210223_0705'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customshapefile',
            name='geom',
            field=django.contrib.gis.db.models.fields.GeometryCollectionField(blank=True, null=True, srid=4326),
        ),
    ]
