# Generated by Django 3.2 on 2020-09-04 15:10

import django.contrib.gis.db.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0012_auto_20200903_1101'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminlevelone',
            name='geom',
            field=django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326),
        ),
        migrations.AlterField(
            model_name='adminleveltwo',
            name='cpu',
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AlterField(
            model_name='adminleveltwo',
            name='engtype_2',
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AlterField(
            model_name='adminleveltwo',
            name='hasc_2',
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AlterField(
            model_name='adminleveltwo',
            name='type_2',
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AlterField(
            model_name='adminlevelzero',
            name='cpu',
            field=models.CharField(blank=True, max_length=250),
        ),
    ]