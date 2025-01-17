# Generated by Django 3.2.7 on 2021-10-02 20:00

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('busstops', '0001_squashed_0010_auto_20210930_1810'),
        ('vehicles', '0001_squashed_0017_auto_20210930_2046'),
    ]

    operations = [
        migrations.AddField(
            model_name='livery',
            name='operator',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='busstops.operator'),
        ),
        migrations.AddField(
            model_name='vehicleedit',
            name='score',
            field=models.SmallIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='VehicleEditVote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('positive', models.BooleanField()),
                ('by_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('for_edit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehicleedit')),
            ],
            options={
                'unique_together': {('by_user', 'for_edit')},
            },
        ),
    ]
