"""
Django admin registrations.
"""
from django.contrib import admin
from .models import UserProfile, Location, MenuItem, Order, OrderItem

admin.site.register(UserProfile)
admin.site.register(Location)
admin.site.register(MenuItem)
admin.site.register(Order)
admin.site.register(OrderItem)