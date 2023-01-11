# Generated by Django 3.1 on 2022-04-21 05:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0062_auto_20220216_2343'),
    ]

    operations = [
        migrations.CreateModel(
            name='DataImportSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('raster_data_file', models.FileField(help_text='JSON file that contains definition of rasters to be imported into the system from disk', upload_to='')),
            ],
            options={
                'verbose_name_plural': 'Data Import Settings',
                'abstract': False,
            },
        ),
        migrations.AlterField(
            model_name='publishedcomputation',
            name='computation_type',
            field=models.CharField(choices=[('LULC', 'LULC'), ('LULC Change', 'LULC Change'), ('Forest Change', 'Forest Change'), ('Forest Fire', 'Forest Fire'), ('Forest Fire Risk', 'Forest Fire Risk'), ('SOC', 'SOC'), ('Productivity State', 'Productivity State'), ('Productivity Trajectory', 'Productivity Trajectory'), ('Productivity Performance', 'Productivity Performance'), ('Productivity', 'Productivity'), ('Land Degradation', 'Land Degradation'), ('Aridity Index', 'Aridity Index'), ('Climate Quality Index', 'Climate Quality Index'), ('Soil Quality Index', 'Soil Quality Index'), ('Vegetation Quality Index', 'Vegetation Quality Index'), ('Management Quality Index', 'Management Quality Index'), ('ESAI', 'ESAI'), ('Forest Carbon Emission', 'Forest Carbon Emission'), ('ILSWE', 'ILSWE'), ('RUSLE', 'RUSLE'), ('Coastal Vulnerability Index', 'Coastal Vulnerability Index')], default='', max_length=100),
        ),
    ]