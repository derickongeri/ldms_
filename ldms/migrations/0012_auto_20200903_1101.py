# Generated by Django 3.2 on 2020-09-03 11:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0011_auto_20200903_1038'),
    ]

    operations = [
        migrations.AddField(
            model_name='adminleveltwo',
            name='gid_1',
            field=models.CharField(default='', max_length=250),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='adminleveltwo',
            name='gid_0',
            field=models.CharField(max_length=50),
        ),
    ]