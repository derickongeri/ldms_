# Generated by Django 3.2 on 2020-09-11 12:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0023_rastervaluemapping_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='rastervaluemapping',
            name='color',
            field=models.CharField(default='#FF0000', max_length=50),
        ),
    ]
