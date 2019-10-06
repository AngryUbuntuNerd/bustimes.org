# Generated by Django 2.2.5 on 2019-10-06 18:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('busstops', '0046_auto_20191001_1255'),
    ]

    operations = [
        migrations.CreateModel(
            name='Calendar',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mon', models.BooleanField()),
                ('tue', models.BooleanField()),
                ('wed', models.BooleanField()),
                ('thu', models.BooleanField()),
                ('fri', models.BooleanField()),
                ('sat', models.BooleanField()),
                ('sun', models.BooleanField()),
                ('start_date', models.DateField()),
                ('end_date', models.DateField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Note',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=16)),
                ('text', models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Route',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=255)),
                ('line_brand', models.CharField(max_length=255)),
                ('line_name', models.CharField(max_length=255)),
                ('description', models.CharField(max_length=255)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField(blank=True, null=True)),
                ('service', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='busstops.Service')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='busstops.DataSource')),
            ],
            options={
                'unique_together': {('source', 'code')},
            },
        ),
        migrations.CreateModel(
            name='Trip',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inbound', models.BooleanField(default=False)),
                ('journey_pattern', models.CharField(blank=True, max_length=255)),
                ('destination', models.CharField(blank=True, max_length=255)),
                ('sequence', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('calendar', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bustimes.Calendar')),
                ('notes', models.ManyToManyField(blank=True, to='bustimes.Note')),
                ('route', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bustimes.Route')),
            ],
        ),
        migrations.CreateModel(
            name='StopTime',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stop_code', models.CharField(max_length=255)),
                ('arrival', models.DurationField()),
                ('departure', models.DurationField()),
                ('sequence', models.PositiveSmallIntegerField()),
                ('timing_status', models.CharField(blank=True, max_length=3)),
                ('activity', models.CharField(blank=True, max_length=16)),
                ('trip', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bustimes.Trip')),
            ],
            options={
                'ordering': ('sequence',),
            },
        ),
        migrations.CreateModel(
            name='CalendarDate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('operation', models.BooleanField()),
                ('calendar', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bustimes.Calendar')),
            ],
        ),
    ]
