"""
Django admin registrations.
"""
from django.contrib import admin
from .models import UserProfile, Location, MenuItem, Order, OrderItem

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'merchant', 'restaurant_location', 'price', 'image']
    list_filter = ['restaurant_location', 'merchant']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'merchant', 'restaurant_location', 'status', 'due_time']
    list_filter = ['status', 'restaurant_location']

admin.site.register(UserProfile)
admin.site.register(Location)
admin.site.register(OrderItem)