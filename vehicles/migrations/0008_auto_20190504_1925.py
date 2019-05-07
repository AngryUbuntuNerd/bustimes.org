# Generated by Django 2.2.1 on 2019-05-04 18:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('busstops', '0039_auto_20190401_1253'),
        ('vehicles', '0007_auto_20190409_1934'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='journeycode',
            options={},
        ),
        migrations.AlterModelOptions(
            name='livery',
            options={'ordering': ('name',), 'verbose_name_plural': 'liveries'},
        ),
        migrations.AlterUniqueTogether(
            name='journeycode',
            unique_together={('code', 'service', 'siri_source')},
        ),
    ]
