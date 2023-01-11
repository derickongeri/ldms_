# Generated by Django 3.1 on 2022-02-05 23:15

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import ldms.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ldms', '0060_auto_20211210_1542'),
    ]

    operations = [
        migrations.CreateModel(
            name='PublishedComputation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('computation_type', models.CharField(choices=[('LULC', 'LULC'), ('Forest Change', 'Forest Change'), ('Forest Fire', 'Forest Fire'), ('Forest Fire Risk', 'Forest Fire Risk'), ('SOC', 'SOC'), ('Productivity State', 'Productivity State'), ('Productivity Trajectory', 'Productivity Trajectory'), ('Productivity Performance', 'Productivity Performance'), ('Productivity', 'Productivity'), ('Land Degradation', 'Land Degradation'), ('Aridity Index', 'Aridity Index'), ('Climate Quality Index', 'Climate Quality Index'), ('Soil Quality Index', 'Soil Quality Index'), ('Vegetation Quality Index', 'Vegetation Quality Index'), ('Management Quality Index', 'Management Quality Index'), ('ESAI', 'ESAI'), ('Forest Carbon Emission', 'Forest Carbon Emission'), ('ILSWE', 'ILSWE'), ('RUSLE', 'RUSLE'), ('Coastal Vulnerability Index', 'Coastal Vulnerability Index')], default='', max_length=100)),
                ('description', models.CharField(blank=True, max_length=100, null=True, verbose_name='Description of the computation')),
                ('published', models.BooleanField(default=True, help_text='If checked, only the specified years will be enabled for computation', null=True)),
                ('admin_zero', models.ForeignKey(blank=True, default='', help_text='Associated country. Leave blank to associate with all countries', null=True, on_delete=django.db.models.deletion.CASCADE, to='ldms.adminlevelzero')),
            ],
            options={
                'verbose_name_plural': 'Published Computations',
                'abstract': False,
            },
        ),
        migrations.AlterField(
            model_name='raster',
            name='raster_year',
            field=models.PositiveIntegerField(default=2022, validators=[django.core.validators.MinValueValidator, ldms.models.max_year_validator]),
        ),
        migrations.CreateModel(
            name='PublishedComputationYear',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('published_year', models.PositiveIntegerField(default=2022, validators=[django.core.validators.MinValueValidator, ldms.models.max_year_validator])),
                # ('created_on', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created on')),
                # ('updated_on', models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True, verbose_name='updated on')),
                # ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='created by')),
                ('published_computation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='published_computations', to='ldms.publishedcomputation', verbose_name='published_computation')),
                # ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='updated by')),
            ],
        ),
    ]