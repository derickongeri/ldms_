# Generated by Django 3.1 on 2021-02-23 07:05

from django.conf import settings
import django.contrib.gis.db.models.fields
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import ldms.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ldms', '0055_auto_20201206_1338'),
    ]

    operations = [
        migrations.AlterField(
            model_name='raster',
            name='raster_category',
            field=models.CharField(blank=True, choices=[('NDVI', 'NDVI'), ('LULC', 'LULC'), ('SOC', 'SOC'), ('Rainfall', 'Rainfall'), ('Aspect', 'Aspect'), ('Forest Loss', 'Forest Loss'), ('SAVI', 'SAVI'), ('MSAVI', 'MSAVI'), ('Evapotranspiration', 'Evapotranspiration'), ('Ecological Units', 'Ecological Units'), ('Soil Slope', 'Soil Slope'), ('Soil Group', 'Soil Group'), ('Soil Drainage', 'Soil Drainage'), ('Soil Parent Material', 'Soil Parent Material'), ('Soil Texture', 'Soil Texture'), ('Soil Rock Fragments', 'Soil Rock Fragments'), ('Population Density', 'Population Density'), ('Land Use Density', 'Land Use Density'), ('Fire Risk', 'Fire Risk'), ('Erosion Protection', 'Erosion Protection'), ('Drought Resistance', 'Drought Resistance'), ('Plant Cover', 'Plant Cover'), ('Aridity Index', 'Aridity Index')], default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='raster',
            name='raster_year',
            field=models.PositiveIntegerField(blank=True, default=2021, validators=[django.core.validators.MinValueValidator, ldms.models.max_year_validator]),
        ),
        migrations.CreateModel(
            name='CustomShapeFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=100, null=True, verbose_name='Description of the vector')),
                ('file', models.FileField(upload_to='', verbose_name='Upload Shapefile')),
                ('shape_length', models.FloatField(blank=True, default=0, null=True)),
                ('shape_area', models.FloatField(blank=True, default=0, null=True)),
                ('geom', django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
