# Generated by Django 2.2.10 on 2020-02-09 18:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0024_auto_20200206_1228'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vehicleedit',
            name='approved',
            field=models.BooleanField(db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='vehicleedit',
            name='url',
            field=models.URLField(blank=True, max_length=255),
        ),
    ]