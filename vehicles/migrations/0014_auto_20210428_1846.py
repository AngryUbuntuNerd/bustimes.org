# Generated by Django 3.2 on 2021-04-28 17:46

from django.db import migrations, models
import django.db.models.expressions
import django.db.models.functions.datetime


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0013_auto_20210218_1332'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='vehiclejourney',
            index_together=set(),
        ),
        migrations.AddIndex(
            model_name='vehiclejourney',
            index=models.Index(django.db.models.expressions.F('service'), django.db.models.expressions.OrderBy(django.db.models.functions.datetime.TruncDate('datetime')), name='service_datetime_date'),
        ),
    ]