# Generated by Django 3.2.3 on 2021-05-14 15:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bustimes', '0006_auto_20210115_1956'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='calendar',
            name='dates',
        ),
        migrations.RemoveField(
            model_name='calendardate',
            name='dates',
        ),
        migrations.RemoveField(
            model_name='route',
            name='dates',
        ),
        migrations.AddField(
            model_name='trip',
            name='vehicle_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='bustimes.vehicletype'),
        ),
        migrations.CreateModel(
            name='CalendarBankHoliday',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operation', models.BooleanField()),
                ('bank_holiday', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bustimes.bankholiday')),
                ('calendar', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bustimes.calendar')),
            ],
            options={
                'unique_together': {('bank_holiday', 'calendar')},
            },
        ),
        migrations.AddField(
            model_name='calendar',
            name='bank_holidays',
            field=models.ManyToManyField(through='bustimes.CalendarBankHoliday', to='bustimes.BankHoliday'),
        ),
    ]
