# Generated by Django 3.2 on 2020-10-27 20:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0032_raster_admin_zero'),
    ]

    operations = [
        migrations.AlterField(
            model_name='raster',
            name='raster_category',
            field=models.CharField(blank=True, choices=[('LULC', 'LULC'), ('SOC', 'SOC'), ('NDVI', 'NDVI'), ('Rainfall', 'Rainfall'), ('Ecological Units', 'Ecological Units'), ('Forest Loss', 'Forest Loss')], default='', max_length=100),
        ),
    ]