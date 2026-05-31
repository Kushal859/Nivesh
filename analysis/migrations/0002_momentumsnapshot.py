from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0001_initial'),
        ('companies', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MomentumSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period', models.CharField(choices=[('3m', '3 Month'), ('6m', '6 Month'), ('12m', '12 Month')], max_length=5)),
                ('return_1m',  models.DecimalField(decimal_places=2, max_digits=8,  null=True)),
                ('return_3m',  models.DecimalField(decimal_places=2, max_digits=8,  null=True)),
                ('return_6m',  models.DecimalField(decimal_places=2, max_digits=8,  null=True)),
                ('return_12m', models.DecimalField(decimal_places=2, max_digits=8,  null=True)),
                ('rsi_14',     models.DecimalField(decimal_places=2, max_digits=6,  null=True)),
                ('ma_20',      models.DecimalField(decimal_places=2, max_digits=10, null=True)),
                ('ma_50',      models.DecimalField(decimal_places=2, max_digits=10, null=True)),
                ('ma_200',     models.DecimalField(decimal_places=2, max_digits=10, null=True)),
                ('high_52w',   models.DecimalField(decimal_places=2, max_digits=10, null=True)),
                ('low_52w',    models.DecimalField(decimal_places=2, max_digits=10, null=True)),
                ('current_price', models.DecimalField(decimal_places=2, max_digits=10, null=True)),
                ('signal',     models.CharField(blank=True, max_length=30)),
                ('emotion',    models.CharField(blank=True, max_length=30)),
                ('emotion_icon', models.CharField(blank=True, max_length=4)),
                ('promoter_current',  models.DecimalField(decimal_places=2, max_digits=5, null=True)),
                ('promoter_trend_6q', models.DecimalField(decimal_places=2, max_digits=5, null=True)),
                ('fii_current',  models.DecimalField(decimal_places=2, max_digits=5, null=True)),
                ('fii_trend_6q', models.DecimalField(decimal_places=2, max_digits=5, null=True)),
                ('dii_current',  models.DecimalField(decimal_places=2, max_digits=5, null=True)),
                ('dii_trend_6q', models.DecimalField(decimal_places=2, max_digits=5, null=True)),
                ('pledging',     models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('computed_at',  models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='momentum', to='companies.company')),
            ],
            options={'db_table': 'momentum_snapshots', 'ordering': ['company', 'period'],
                     'unique_together': {('company', 'period')}},
        ),
    ]
