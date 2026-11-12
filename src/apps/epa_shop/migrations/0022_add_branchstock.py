import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('companies', '0017_alter_businesstype_name'),
        ('company', '0009_expense_paid_by_expense_updated_by'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('epa_shop', '0021_sale_cogs_amount_saleitem_cogs_amount_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BranchStock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField(db_index=True)),
                ('quantity_in_stock', models.IntegerField(default=0)),
                ('minimum_stock_level', models.IntegerField(default=2)),
                ('maximum_stock_level', models.IntegerField(blank=True, default=100, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_stocks', to='company.branch')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_stocks', to='companies.company')),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
            ],
            options={
                'db_table': 'epa_branch_stocks',
                'unique_together': {('branch', 'content_type', 'object_id')},
            },
        ),
        migrations.CreateModel(
            name='StockTransfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField(db_index=True)),
                ('quantity', models.PositiveIntegerField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('in_transit', 'In Transit'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('transfer_number', models.CharField(blank=True, max_length=50, unique=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_transfers', to='companies.company')),
                ('completed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_transfers_completed', to=settings.AUTH_USER_MODEL)),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_transfers_created', to=settings.AUTH_USER_MODEL)),
                ('from_branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_transfers_from', to='company.branch')),
                ('to_branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_transfers_to', to='company.branch')),
            ],
            options={
                'db_table': 'epa_stock_transfers',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='phone',
            name='total_quantity_in_stock',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='electronic',
            name='total_quantity_in_stock',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='accessory',
            name='total_quantity_in_stock',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='unit',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='units', to='company.branch'),
        ),
    ]