# Generated by Django 3.2 on 2020-09-20 09:34
import django.contrib.gis.db.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0025_alter_rastervaluemapping_color'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegionalAdminLevel',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.IntegerField()),
                ('shape_area', models.FloatField(blank=True, max_length=100, null=True)),
                ('shape_length', models.FloatField(blank=True, max_length=16, null=True)),
                ('geom', django.contrib.gis.db.models.fields.MultiPolygonField(default=None, srid=4326)),
            ],
        ),
        migrations.AlterModelOptions(
            name='raster',
            options={'ordering': ['raster_year']},
        ),
    ]
