# Generated by Django 3.2.8 on 2021-10-22 13:39

from django.db import migrations, models
import django.db.models.functions.text


class Migration(migrations.Migration):

    dependencies = [
        ('bustimes', '0001_squashed_0012_alter_route_revision_number'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='route',
            index=models.Index(django.db.models.functions.text.Upper('line_name'), name='route_line_name'),
        ),
    ]
