"""
Core data models for SwiftDeliver.
"""
from django.db import models
from django.contrib.auth.models import User


# ==================== MODEL: UserProfile ====================
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('CUSTOMER', 'Customer'),
        ('MERCHANT', 'Merchant'),
        ('COURIER', 'Courier'),
        ('ADMIN', 'Administrator'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='userprofile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='CUSTOMER')
    is_approved = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


# ==================== MODEL: Location ====================
class Location(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    is_restaurant = models.BooleanField(default=False)
    matrix_id = models.IntegerField(unique=True)  # 0-8 index for travel matrix
    grid_x = models.IntegerField(default=0)       # Canvas X coordinate
    grid_y = models.IntegerField(default=0)       # Canvas Y coordinate

    def __str__(self):
        return self.name


# ==================== MODEL: MenuItem ====================
class MenuItem(models.Model):
    merchant = models.ForeignKey(
        User, on_delete=models.CASCADE,
        limit_choices_to={'userprofile__role': 'MERCHANT'},
        related_name='menu_items'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.name


# ==================== MODEL: Order ====================
class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING_MERCHANT', 'Pending Merchant Approval'),  # NEW: Customer placed, waiting merchant
        ('PREPARING', 'Preparing'),                          # NEW: Merchant accepted, making food
        ('READY_FOR_PICKUP', 'Ready for Pickup'),           # NEW: Food ready, waiting courier
        ('PENDING_COURIER', 'Pending Courier'),             # Available for courier acceptance
        ('ACCEPTED', 'Accepted'),                            # Courier accepted
        ('OUT_FOR_DELIVERY', 'Out for Delivery'),           # Courier delivering
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_orders')
    merchant = models.ForeignKey(
        User, on_delete=models.CASCADE,
        limit_choices_to={'userprofile__role': 'MERCHANT'},
        related_name='merchant_orders'
    )
    courier = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        limit_choices_to={'userprofile__role': 'COURIER'},
        related_name='courier_orders'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING_MERCHANT')
    destination = models.ForeignKey(Location, on_delete=models.CASCADE)
    due_time = models.DateTimeField()
    notes = models.TextField(blank=True)
    route_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Order #{self.id} - {self.status}"


# ==================== MODEL: OrderItem ====================
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    @property
    def line_total(self):
        return self.menu_item.price * self.quantity


# ==================== SIGNAL: Auto-create UserProfile on User creation ====================
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance, defaults={'role': 'CUSTOMER', 'is_approved': True})


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'userprofile'):
        instance.userprofile.save()