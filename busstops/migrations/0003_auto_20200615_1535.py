# Generated by Django 3.0.7 on 2020-06-15 14:35

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('busstops', '0002_auto_20200610_1632'),
    ]

    operations = [
        migrations.AlterField(
            model_name='service',
            name='region',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='busstops.Region'),
        ),
        migrations.CreateModel(
            name='ServiceColour',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64)),
                ('foreground', models.CharField(blank=True, max_length=20)),
                ('background', models.CharField(blank=True, max_length=20)),
                ('operator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='busstops.Operator')),
            ],
        ),
        migrations.AddField(
            model_name='service',
            name='colour',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='busstops.ServiceColour'),
        ),
    ]