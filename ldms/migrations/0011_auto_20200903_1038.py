# Generated by Django 3.2 on 2020-09-03 10:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ldms', '0010_auto_20200903_0913'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminlevelone',
            name='cc_1',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AlterField(
            model_name='adminlevelone',
            name='nl_name_1',
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AlterField(
            model_name='adminlevelone',
            name='varname_1',
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AlterField(
            model_name='adminleveltwo',
            name='cc_2',
            field=models.CharField(blank=True, default='', max_length=250),
        ),
        migrations.AlterField(
            model_name='adminleveltwo',
            name='nl_name_1',
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AlterField(
            model_name='adminleveltwo',
            name='nl_name_2',
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AlterField(
            model_name='adminleveltwo',
            name='varname_2',
            field=models.CharField(blank=True, max_length=250),
        ),
    ]