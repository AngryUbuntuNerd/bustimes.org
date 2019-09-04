# Generated by Django 2.2.5 on 2019-09-04 10:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0014_auto_20190904_0259'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehiclelocation',
            name='current',
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name='vehiclelocation',
            index=models.Index(condition=models.Q(current=True), fields=['current', '-datetime'], name='datetime'),
        ),
    ]
