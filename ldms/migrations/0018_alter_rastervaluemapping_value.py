# Generated by Django 3.2 on 2020-09-10 13:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0017_auto_20200910_1315'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rastervaluemapping',
            name='value',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
