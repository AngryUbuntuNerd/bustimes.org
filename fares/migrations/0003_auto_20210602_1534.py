# Generated by Django 3.2.3 on 2021-06-02 14:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fares', '0002_auto_20210306_0911'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataset',
            name='published',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tariff',
            name='access_zones',
            field=models.ManyToManyField(to='fares.FareZone'),
        ),
        migrations.AlterField(
            model_name='dataset',
            name='description',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='tariff',
            name='trip_type',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='tariff',
            name='type_of_tariff',
            field=models.CharField(blank=True, choices=[('point_to_point', 'Point to point'), ('zonal', 'Zonal')], max_length=19),
        ),
    ]
