# Generated by Django 3.1.3 on 2020-11-21 09:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_auto_20200930_1131'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='trusted',
            field=models.BooleanField(null=True),
        ),
    ]