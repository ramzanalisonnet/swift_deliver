# Generated manually for SwiftDeliver

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Location',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('address', models.CharField(max_length=255)),
                ('is_restaurant', models.BooleanField(default=False)),
                ('matrix_id', models.IntegerField(unique=True)),
                ('grid_x', models.IntegerField(default=0)),
                ('grid_y', models.IntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name='MenuItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('merchant', models.ForeignKey(limit_choices_to={'userprofile__role': 'MERCHANT'}, on_delete=django.db.models.deletion.CASCADE, related_name='menu_items', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('CUSTOMER', 'Customer'), ('MERCHANT', 'Merchant'), ('COURIER', 'Courier'), ('ADMIN', 'Administrator')], default='CUSTOMER', max_length=20)),
                ('is_approved', models.BooleanField(default=False)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='userprofile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('PENDING', 'Pending Courier'), ('ACCEPTED', 'Accepted'), ('OUT_FOR_DELIVERY', 'Out for Delivery'), ('DELIVERED', 'Delivered'), ('CANCELLED', 'Cancelled')], default='PENDING', max_length=20)),
                ('due_time', models.DateTimeField()),
                ('notes', models.TextField(blank=True)),
                ('route_data', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('courier', models.ForeignKey(blank=True, limit_choices_to={'userprofile__role': 'COURIER'}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='courier_orders', to=settings.AUTH_USER_MODEL)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_orders', to=settings.AUTH_USER_MODEL)),
                ('destination', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='delivery.location')),
                ('merchant', models.ForeignKey(limit_choices_to={'userprofile__role': 'MERCHANT'}, on_delete=django.db.models.deletion.CASCADE, related_name='merchant_orders', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('menu_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='delivery.menuitem')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='delivery.order')),
            ],
        ),
    ]