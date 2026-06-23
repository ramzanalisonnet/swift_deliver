"""
All views and API endpoints for SwiftDeliver.
"""
import json
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import UserProfile, Location, MenuItem, Order, OrderItem
from .utils import (
    LOCATIONS_DATA, ensure_locations,
    calculate_nearest_neighbor_route, validate_route_feasibility
)


# ==================== FUNCTION: login_view ====================
def login_view(request):
    """
    Authenticate users. Blocks unapproved Merchant/Courier accounts.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            # Ensure user has a profile (for users created before signals or via createsuperuser)
            try:
                profile = user.userprofile
            except UserProfile.DoesNotExist:
                profile = UserProfile.objects.create(user=user, role='CUSTOMER', is_approved=True)
            
            if profile.role in ['MERCHANT', 'COURIER'] and not profile.is_approved:
                return JsonResponse({'success': False, 'error': 'Your account is pending administrator approval.'})
            login(request, user)
            return JsonResponse({'success': True, 'redirect': '/dashboard/'})
        return JsonResponse({'success': False, 'error': 'Invalid username or password.'})
    return render(request, 'login.html')


# ==================== FUNCTION: register_view ====================
def register_view(request):
    """
    Register new users. Customers are auto-approved;
    Merchants and Couriers start as pending.
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        role = data.get('role', 'CUSTOMER')

        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'error': 'Username already taken.'})

        user = User.objects.create_user(username=username, email=email, password=password)
        approved = True if role == 'CUSTOMER' else False

        # Use get_or_create because post_save signal may have already created a profile
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.is_approved = approved
        profile.save()

        msg = 'Registration successful! Please log in.'
        if not approved:
            msg = 'Registration successful. Your account is pending admin approval.'
        return JsonResponse({'success': True, 'message': msg})
    return render(request, 'register.html')


# ==================== FUNCTION: logout_view ====================
@login_required
def logout_view(request):
    """Terminate session and redirect to login."""
    logout(request)
    return redirect('login')


# ==================== FUNCTION: dashboard_router ====================
@login_required
def dashboard_router(request):
    """Redirect to role-specific dashboard."""
    role = request.user.userprofile.role
    if role == 'CUSTOMER':
        return redirect('customer_dashboard')
    elif role == 'MERCHANT':
        return redirect('merchant_dashboard')
    elif role == 'COURIER':
        return redirect('courier_dashboard')
    elif role == 'ADMIN':
        return redirect('admin_dashboard')
    return redirect('login')


# ==================== FUNCTION: customer_dashboard ====================
@login_required
def customer_dashboard(request):
    """Render customer dashboard with merchants and order history."""
    if request.user.userprofile.role != 'CUSTOMER':
        return redirect('dashboard')
    merchants = User.objects.filter(userprofile__role='MERCHANT', userprofile__is_approved=True)
    orders = Order.objects.filter(customer=request.user).order_by('-created_at')
    locations = Location.objects.filter(is_restaurant=False)
    return render(request, 'customer_dashboard.html', {
        'merchants': merchants,
        'orders': orders,
        'locations': locations
    })


# ==================== FUNCTION: merchant_dashboard ====================
@login_required
def merchant_dashboard(request):
    """Render merchant dashboard with menu items, order creation and history."""
    if request.user.userprofile.role != 'MERCHANT':
        return redirect('dashboard')
    ensure_locations()
    locations = Location.objects.filter(is_restaurant=False)
    orders = Order.objects.filter(merchant=request.user).order_by('-created_at')
    menu_items = MenuItem.objects.filter(merchant=request.user).order_by('-id')
    return render(request, 'merchant_dashboard.html', {
        'locations': locations,
        'orders': orders,
        'menu_items': menu_items
    })


# ==================== FUNCTION: courier_dashboard ====================
@login_required
def courier_dashboard(request):
    """Render courier dashboard with available and active deliveries."""
    if request.user.userprofile.role != 'COURIER':
        return redirect('dashboard')
    ensure_locations()
    available = Order.objects.filter(status='PENDING', courier__isnull=True).select_related('destination', 'merchant')
    my_orders = Order.objects.filter(courier=request.user).exclude(status='DELIVERED').select_related('destination')
    return render(request, 'courier_dashboard.html', {
        'available_orders': available,
        'my_orders': my_orders
    })


# ==================== FUNCTION: courier_map ====================
@login_required
def courier_map(request):
    """Render the simulated map canvas for active delivery route."""
    if request.user.userprofile.role != 'COURIER':
        return redirect('dashboard')
    return render(request, 'courier_map.html', {'locations': LOCATIONS_DATA})


# ==================== FUNCTION: admin_dashboard ====================
@login_required
def admin_dashboard(request):
    """Render admin management panel."""
    if request.user.userprofile.role != 'ADMIN':
        return redirect('dashboard')
    users = User.objects.all().select_related('userprofile').order_by('-date_joined')
    orders = Order.objects.all().select_related('customer', 'merchant', 'courier', 'destination').order_by('-created_at')
    return render(request, 'admin_dashboard.html', {
        'users': users,
        'orders': orders,
        'roles': UserProfile.ROLE_CHOICES
    })


# ==================== API: get_merchants ====================
@login_required
def api_merchants(request):
    """JSON endpoint: list all approved merchants."""
    merchants = User.objects.filter(userprofile__role='MERCHANT', userprofile__is_approved=True)
    data = [{'id': m.id, 'name': m.username, 'email': m.email} for m in merchants]
    return JsonResponse({'merchants': data})


# ==================== API: get_menu ====================
@login_required
def api_menu(request, merchant_id):
    """JSON endpoint: menu items for a merchant."""
    items = MenuItem.objects.filter(merchant_id=merchant_id)
    data = [{'id': i.id, 'name': i.name, 'description': i.description, 'price': float(i.price)} for i in items]
    return JsonResponse({'items': data})


# ==================== API: place_order ====================
@login_required
@csrf_exempt
def api_place_order(request):
    """
    Customer places an order with multiple items and quantities.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})
    data = json.loads(request.body)
    merchant_id = data.get('merchant_id')
    item_list = data.get('items', [])
    destination_id = data.get('destination_id')

    if not item_list:
        return JsonResponse({'success': False, 'error': 'Your cart is empty.'})

        # Handle due time
    due_time_str = data.get('due_time')
    if due_time_str:
        try:
            # Parse ISO format datetime (from datetime-local input)
            from datetime import datetime
            # Remove 'Z' or timezone info if present, then parse
            due_time_str = due_time_str.replace('Z', '').replace('z', '')
            if '.' in due_time_str:
                due_time_str = due_time_str.split('.')[0]
            due_time = datetime.fromisoformat(due_time_str.replace('T', ' ').replace('t', ' '))
            # Make it timezone-aware
            from django.utils import timezone
            if timezone.is_naive(due_time):
                due_time = timezone.make_aware(due_time)
        except (ValueError, TypeError):
            due_time = timezone.now() + timezone.timedelta(hours=2)
    else:
        due_time = timezone.now() + timezone.timedelta(hours=2)

    order = Order.objects.create(
        customer=request.user,
        merchant_id=merchant_id,
        destination_id=destination_id,
        status='PENDING',
        due_time=due_time
    )
    total = 0
    for entry in item_list:
        mi = MenuItem.objects.get(id=entry['id'])
        qty = entry.get('quantity', 1)
        OrderItem.objects.create(order=order, menu_item=mi, quantity=qty)
        total += float(mi.price) * qty

    return JsonResponse({'success': True, 'order_id': order.id, 'total': round(total, 2)})


# ==================== API: merchant_create_order ====================
@login_required
@csrf_exempt
def api_merchant_create_order(request):
    """
    Merchant creates a direct delivery order with items.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False})
    
    data = json.loads(request.body)
    items = data.get('items', [])
    
    order = Order.objects.create(
        merchant=request.user,
        customer=request.user,
        destination_id=data.get('destination_id'),
        due_time=data.get('due_time'),
        notes=data.get('notes', ''),
        status='PENDING'
    )
    
    # Add order items
    for entry in items:
        menu_item = MenuItem.objects.get(id=entry['id'], merchant=request.user)
        OrderItem.objects.create(order=order, menu_item=menu_item, quantity=entry['quantity'])
    
    return JsonResponse({'success': True, 'order_id': order.id})


# ==================== API: get_orders ====================
@login_required
def api_orders(request):
    """JSON endpoint: fetch orders filtered by authenticated user's role."""
    role = request.user.userprofile.role
    if role == 'CUSTOMER':
        qs = Order.objects.filter(customer=request.user)
    elif role == 'MERCHANT':
        qs = Order.objects.filter(merchant=request.user)
    elif role == 'COURIER':
        qs = Order.objects.filter(courier=request.user)
    else:
        qs = Order.objects.none()

    data = []
    for o in qs:
        items = [{'name': i.menu_item.name, 'qty': i.quantity, 'price': float(i.menu_item.price)} for i in o.items.all()]
        data.append({
            'id': o.id,
            'status': o.status,
            'destination': o.destination.address if o.destination else '',
            'due_time': o.due_time.isoformat() if o.due_time else None,
            'notes': o.notes,
            'items': items,
            'courier': o.courier.username if o.courier else None,
            'created_at': o.created_at.isoformat()
        })
    return JsonResponse({'orders': data})


# ==================== API: accept_orders ====================
@login_required
@csrf_exempt
def api_accept_orders(request):
    """
    Courier accepts multiple orders.
    Runs nearest-neighbor feasibility check against due times.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})
    data = json.loads(request.body)
    order_ids = data.get('order_ids', [])

    if not order_ids:
        return JsonResponse({'success': False, 'error': 'No orders selected.'})

    orders = list(Order.objects.filter(id__in=order_ids, status='PENDING', courier__isnull=True))
    if len(orders) != len(order_ids):
        return JsonResponse({'success': False, 'error': 'Some orders are no longer available.'})

    destination_ids = []
    due_times = {}
    for o in orders:
        if o.destination:
            mid = o.destination.matrix_id
            destination_ids.append(mid)
            # Make due_time timezone-aware if it's naive
            due = o.due_time
            if due is not None and timezone.is_naive(due):
                due = timezone.make_aware(due)
            due_times[mid] = due

    # Use timezone-aware start time
    start_time = timezone.now()

    is_feasible, route, details = validate_route_feasibility(destination_ids, due_times, start_time)

    if not is_feasible:
        failed = next(d for d in details if not d['on_time'])
        return JsonResponse({
            'success': False,
            'error': f"Cannot accept Order: Cannot deliver to {failed['location_name']} by due time. Estimated arrival is {failed['arrival']}."
        })

    for o in orders:
        o.courier = request.user
        o.status = 'ACCEPTED'
        o.route_data = {'route': route, 'details': details, 'started_at': start_time.isoformat()}
        o.save()

    return JsonResponse({'success': True, 'route': route, 'details': details})


# ==================== API: update_status ====================
@login_required
@csrf_exempt
def api_update_status(request):
    """Update order status (e.g., mark DELIVERED)."""
    if request.method != 'POST':
        return JsonResponse({'success': False})
    data = json.loads(request.body)
    order = get_object_or_404(Order, id=data.get('order_id'), courier=request.user)
    order.status = data.get('status', order.status)
    if order.status == 'DELIVERED':
        order.delivered_at = timezone.now()
    order.save()
    return JsonResponse({'success': True})


# ==================== API: merchant_add_menu_item ====================
@login_required
@csrf_exempt
def api_add_menu_item(request):
    """
    Merchant adds a new menu item to their restaurant.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})
    
    if request.user.userprofile.role != 'MERCHANT':
        return JsonResponse({'success': False, 'error': 'Only merchants can add menu items.'})
    
    data = json.loads(request.body)
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    price = data.get('price', 0)
    
    if not name or float(price) <= 0:
        return JsonResponse({'success': False, 'error': 'Name and valid price are required.'})
    
    item = MenuItem.objects.create(
        merchant=request.user,
        name=name,
        description=description,
        price=float(price)
    )
    return JsonResponse({'success': True, 'item_id': item.id, 'name': item.name})


# ==================== API: courier_route ====================
@login_required
def api_courier_route(request):
    """Return active route data for map visualization."""
    orders = Order.objects.filter(courier=request.user).exclude(status='DELIVERED')
    if not orders.exists():
        return JsonResponse({'success': False, 'error': 'No active deliveries.'})
    rd = orders.first().route_data
    return JsonResponse({
        'success': True,
        'locations': LOCATIONS_DATA,
        'route': rd.get('route', []),
        'details': rd.get('details', [])
    })


# ==================== API: admin_users ====================
@login_required
def api_admin_users(request):
    """Admin: list all users."""
    if request.user.userprofile.role != 'ADMIN':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    users = User.objects.all().select_related('userprofile')
    data = [{
        'id': u.id, 'username': u.username, 'email': u.email,
        'role': u.userprofile.role, 'is_approved': u.userprofile.is_approved
    } for u in users]
    return JsonResponse({'users': data})


# ==================== API: approve_user ====================
@login_required
@csrf_exempt
def api_approve_user(request):
    """Admin: approve a pending Merchant or Courier."""
    if request.method != 'POST':
        return JsonResponse({'success': False})
    data = json.loads(request.body)
    user = get_object_or_404(User, id=data.get('user_id'))
    user.userprofile.is_approved = True
    user.userprofile.save()
    return JsonResponse({'success': True})


# ==================== API: transfer_role ====================
@login_required
@csrf_exempt
def api_transfer_role(request):
    """Admin: change a user's role."""
    if request.method != 'POST':
        return JsonResponse({'success': False})
    data = json.loads(request.body)
    user = get_object_or_404(User, id=data.get('user_id'))
    new_role = data.get('new_role')
    user.userprofile.role = new_role
    if new_role == 'CUSTOMER':
        user.userprofile.is_approved = True
    user.userprofile.save()
    return JsonResponse({'success': True})


# ==================== API: admin_orders ====================
@login_required
def api_admin_orders(request):
    """Admin: list all orders."""
    if request.user.userprofile.role != 'ADMIN':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    orders = Order.objects.all().order_by('-created_at')
    data = [{
        'id': o.id, 'customer': o.customer.username,
        'merchant': o.merchant.username if o.merchant else '',
        'courier': o.courier.username if o.courier else '',
        'status': o.status, 'destination': o.destination.address if o.destination else '',
        'due_time': o.due_time.isoformat() if o.due_time else None
    } for o in orders]
    return JsonResponse({'orders': data})


# ==================== API: admin_update_order ====================
@login_required
@csrf_exempt
def api_admin_update_order(request):
    """Admin: update status or delete an order."""
    if request.method != 'POST':
        return JsonResponse({'success': False})
    data = json.loads(request.body)
    order = get_object_or_404(Order, id=data.get('order_id'))
    action = data.get('action')
    if action == 'delete':
        order.delete()
    else:
        order.status = data.get('status', order.status)
        order.save()
    return JsonResponse({'success': True})