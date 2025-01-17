# Generated by Django 3.2.7 on 2021-10-01 09:30

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    replaces = [('vosa', '0001_initial'), ('vosa', '0002_auto_20201121_0959'), ('vosa', '0003_auto_20210824_1210'), ('vosa', '0004_auto_20210913_1429')]

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Licence',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('trading_name', models.CharField(blank=True, max_length=255)),
                ('traffic_area', models.CharField(choices=[('H', 'West of England'), ('D', 'West Midlands'), ('G', 'Wales'), ('K', 'London and the South East of England'), ('M', 'Scotland'), ('C', 'North West of England'), ('B', 'North East of England'), ('F', 'East of England')], max_length=1)),
                ('licence_number', models.CharField(max_length=20, unique=True)),
                ('discs', models.PositiveSmallIntegerField()),
                ('authorised_discs', models.PositiveSmallIntegerField()),
                ('address', models.TextField(default='')),
                ('description', models.CharField(choices=[('Restricted', 'Restricted'), ('Standard International', 'Standard International'), ('Standard National', 'Standard National')], max_length=22)),
                ('granted_date', models.DateField(blank=True, null=True)),
                ('expiry_date', models.DateField(blank=True, null=True)),
                ('licence_status', models.CharField(default='', max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Registration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('registration_number', models.CharField(max_length=20, unique=True)),
                ('service_number', models.CharField(max_length=100)),
                ('start_point', models.CharField(max_length=255)),
                ('finish_point', models.CharField(max_length=255)),
                ('via', models.CharField(blank=True, max_length=255)),
                ('subsidies_description', models.CharField(max_length=255)),
                ('subsidies_details', models.CharField(max_length=255)),
                ('registration_status', models.CharField(db_index=True, max_length=255)),
                ('traffic_area_office_covered_by_area', models.CharField(max_length=100)),
                ('licence', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vosa.licence')),
                ('service_type_description', models.CharField(blank=True, max_length=255)),
                ('authority_description', models.CharField(default='', max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Variation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('variation_number', models.PositiveSmallIntegerField()),
                ('effective_date', models.DateField(blank=True, null=True)),
                ('date_received', models.DateField(blank=True, null=True)),
                ('end_date', models.DateField(blank=True, null=True)),
                ('service_type_other_details', models.TextField()),
                ('registration_status', models.CharField(max_length=255)),
                ('publication_text', models.TextField()),
                ('short_notice', models.CharField(max_length=255)),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vosa.registration')),
            ],
            options={
                'ordering': ('-variation_number',),
                'unique_together': {('registration', 'variation_number')},
            },
        ),
        migrations.AddField(
            model_name='registration',
            name='latest_variation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='latest', to='vosa.variation'),
        ),
        migrations.AddField(
            model_name='registration',
            name='registered',
            field=models.BooleanField(default=False),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='registration',
            name='authority_description',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='registration',
            name='finish_point',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='registration',
            name='service_number',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='registration',
            name='start_point',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='registration',
            name='subsidies_details',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
