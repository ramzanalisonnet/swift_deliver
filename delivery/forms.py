"""
Django forms for SwiftDeliver.
"""
from django import forms
from .models import MenuItem, Order

class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ['name', 'description', 'price', 'image', 'restaurant_location']

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['destination', 'due_time', 'notes']