# Generated by Django 3.1 on 2020-11-12 16:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0033_alter_raster_raster_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScheduledTask',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner', models.CharField(max_length=128)),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('name', models.CharField(max_length=128)),
                ('job_id', models.CharField(max_length=128)),
                ('result', models.TextField(blank=True, null=True)),
                ('error', models.TextField(blank=True, null=True)),
                ('method', models.CharField(max_length=128)),
                ('args', models.TextField(blank=True, null=True)),
                ('request', models.TextField(blank=True, null=True)),
                ('status', models.CharField(max_length=50)),
                ('succeeded', models.BooleanField(default=False)),
                ('completed_on', models.DateTimeField(blank=True, null=True)),
                ('notified_owner', models.BooleanField(default=False)),
                ('notified_on', models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.AlterField(
            model_name='raster',
            name='raster_category',
            field=models.CharField(blank=True, choices=[('LULC', 'LULC'), ('SOC', 'SOC'), ('NDVI', 'NDVI'), ('Rainfall', 'Rainfall'), ('Ecological Units', 'Ecological Units'), ('Forest Loss', 'Forest Loss'), ('SAVI', 'SAVI'), ('MSAVI', 'MSAVI')], default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='raster',
            name='raster_source',
            field=models.CharField(blank=True, choices=[('LULC', 'LULC'), ('Modis', 'Modis'), ('Landsat 7', 'Landsat 7'), ('Landsat 8', 'Landsat 8'), ('Hansen', 'Hansen')], default='', max_length=50),
        ),
    ]
