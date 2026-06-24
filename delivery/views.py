"""
All views and API endpoints for SwiftDeliver.
"""
import json
from datetime import datetime, timedelta
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
    calculate_nearest_neighbor_route, validate_route_feasibility,
    get_location_data, calculate_due_time, TRAVEL_TIMES
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
    restaurant_locations = Location.objects.filter(is_restaurant=True)

    pending_orders = Order.objects.filter(merchant=request.user, status='PENDING_MERCHANT').order_by('-created_at')
    preparing_orders = Order.objects.filter(merchant=request.user, status='PREPARING').order_by('-created_at')
    ready_orders = Order.objects.filter(merchant=request.user, status='READY_FOR_PICKUP').order_by('-created_at')
    past_orders = Order.objects.filter(merchant=request.user).exclude(
        status__in=['PENDING_MERCHANT', 'PREPARING', 'READY_FOR_PICKUP']
    ).order_by('-created_at')

    orders = Order.objects.filter(merchant=request.user).order_by('-created_at')
    menu_items = MenuItem.objects.filter(merchant=request.user).order_by('-id')
    return render(request, 'merchant_dashboard.html', {
        'locations': locations,
        'restaurant_locations': restaurant_locations,
        'orders': orders,
        'menu_items': menu_items,
        'pending_orders': pending_orders,
        'preparing_orders': preparing_orders,
        'ready_orders': ready_orders,
        'past_orders': past_orders
    })

# ==================== FUNCTION: courier_dashboard ====================
@login_required
def courier_dashboard(request):
    """Render courier dashboard with available and active deliveries."""
    if request.user.userprofile.role != 'COURIER':
        return redirect('dashboard')
    ensure_locations()
    available = Order.objects.filter(status='READY_FOR_PICKUP', courier__isnull=True).select_related('destination', 'merchant', 'restaurant_location')
    my_orders = Order.objects.filter(courier=request.user).exclude(status='DELIVERED').select_related('destination', 'restaurant_location')
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
    orders = Order.objects.all().select_related('customer', 'merchant', 'courier', 'destination', 'restaurant_location').order_by('-created_at')
    return render(request, 'admin_dashboard.html', {
        'users': users,
        'orders': orders,
        'roles': UserProfile.ROLE_CHOICES
    })

# ==================== API: get_merchants ====================
@login_required
def api_merchants(request):
    """JSON endpoint: list all approved merchants with restaurant info."""
    merchants = User.objects.filter(userprofile__role='MERCHANT', userprofile__is_approved=True)
    data = []
    for m in merchants:
        # Get merchant's restaurant location from their menu items
        rest_loc = None
        menu_items = MenuItem.objects.filter(merchant=m).select_related('restaurant_location')
        if menu_items.exists() and menu_items.first().restaurant_location:
            rest_loc = menu_items.first().restaurant_location

        merchant_data = {
            'id': m.id,
            'name': m.username,
            'email': m.email,
        }
        if rest_loc:
            merchant_data['restaurant'] = {
                'id': rest_loc.id,
                'name': rest_loc.name,
                'address': rest_loc.address,
                'matrix_id': rest_loc.matrix_id
            }
        else:
            merchant_data['restaurant'] = None
        data.append(merchant_data)
    return JsonResponse({'merchants': data})

# ==================== API: get_menu ====================
@login_required
def api_menu(request, merchant_id):
    """JSON endpoint: menu items for a merchant, including image_url."""
    items = MenuItem.objects.filter(merchant_id=merchant_id)
    data = [{
        'id': i.id,
        'name': i.name,
        'description': i.description,
        'price': float(i.price),
        'image_url': i.image
    } for i in items]
    return JsonResponse({'items': data})

# ==================== API: place_order ====================
@login_required
@csrf_exempt
def api_place_order(request):
    """
    Customer places an order with multiple items and quantities.
    Due time is auto-calculated from distance if not provided.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})
    data = json.loads(request.body)
    merchant_id = data.get('merchant_id')
    item_list = data.get('items', [])
    destination_id = data.get('destination_id')

    if not item_list:
        return JsonResponse({'success': False, 'error': 'Your cart is empty.'})

    # Get merchant's restaurant location from first menu item
    first_item = MenuItem.objects.filter(id=item_list[0]['id']).select_related('restaurant_location').first()
    if not first_item or not first_item.restaurant_location:
        return JsonResponse({'success': False, 'error': 'Merchant has no restaurant location configured.'})

    restaurant_location = first_item.restaurant_location
    destination = Location.objects.get(id=destination_id)

    # Auto-calculate due time from distance if not provided
    due_time_str = data.get('due_time')
    if due_time_str:
        try:
            due_time = datetime.fromisoformat(due_time_str.replace('T', ' ').replace('t', ' '))
        except (ValueError, TypeError):
            due_time = calculate_due_time(restaurant_location.matrix_id, destination.matrix_id)
    else:
        due_time = calculate_due_time(restaurant_location.matrix_id, destination.matrix_id)

    order = Order.objects.create(
        customer=request.user,
        merchant_id=merchant_id,
        destination_id=destination_id,
        restaurant_location=restaurant_location,
        status='PENDING_MERCHANT',
        due_time=due_time
    )
    total = 0
    for entry in item_list:
        mi = MenuItem.objects.get(id=entry['id'])
        qty = entry.get('quantity', 1)
        OrderItem.objects.create(order=order, menu_item=mi, quantity=qty)
        total += float(mi.price) * qty

    return JsonResponse({
        'success': True,
        'order_id': order.id,
        'total': round(total, 2),
        'due_time': order.due_time.isoformat()
    })

# ==================== API: cancel_order ====================
@login_required
@csrf_exempt
def api_cancel_order(request):
    """
    Customer cancels order within 5 minutes of placement.
    Cannot cancel if courier has already accepted (status beyond PENDING_MERCHANT).
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})

    data = json.loads(request.body)
    order_id = data.get('order_id')

    try:
        order = Order.objects.get(id=order_id, customer=request.user)
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found.'})

    if order.status not in ['PENDING_MERCHANT']:
        return JsonResponse({
            'success': False, 
            'error': 'Cannot cancel: Order is already being prepared or picked up by courier.'
        })

    time_diff = (datetime.now() - order.created_at.replace(tzinfo=None)).total_seconds()
    if time_diff > 300:
        return JsonResponse({
            'success': False, 
            'error': 'Cannot cancel: 5-minute cancellation window has expired.'
        })

    order.status = 'CANCELLED'
    order.save()
    return JsonResponse({'success': True, 'message': 'Order cancelled successfully.'})

# ==================== API: merchant_accept_order ====================
@login_required
@csrf_exempt
def api_merchant_accept_order(request):
    """
    Merchant accepts an order and starts preparing food.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})

    if request.user.userprofile.role != 'MERCHANT':
        return JsonResponse({'success': False, 'error': 'Only merchants can accept orders.'})

    data = json.loads(request.body)
    order_id = data.get('order_id')

    try:
        order = Order.objects.get(id=order_id, merchant=request.user, status='PENDING_MERCHANT')
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found or already processed.'})

    order.status = 'PREPARING'
    order.save()
    return JsonResponse({'success': True, 'message': 'Order accepted. Start preparing food.'})

# ==================== API: merchant_ready_for_pickup ====================
@login_required
@csrf_exempt
def api_merchant_ready_for_pickup(request):
    """
    Merchant marks order as ready for courier pickup.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})

    if request.user.userprofile.role != 'MERCHANT':
        return JsonResponse({'success': False, 'error': 'Only merchants can update order status.'})

    data = json.loads(request.body)
    order_id = data.get('order_id')

    try:
        order = Order.objects.get(id=order_id, merchant=request.user, status='PREPARING')
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found or not in preparing status.'})

    order.status = 'READY_FOR_PICKUP'
    order.save()
    return JsonResponse({'success': True, 'message': 'Order is ready for courier pickup.'})

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
    image_url = data.get('image_url', '').strip()
    restaurant_location_id = data.get('restaurant_location_id')

    if not name or float(price) <= 0:
        return JsonResponse({'success': False, 'error': 'Name and valid price are required.'})

    # Validate restaurant location
    restaurant_location = None
    if restaurant_location_id:
        try:
            restaurant_location = Location.objects.get(id=restaurant_location_id, is_restaurant=True)
        except Location.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Invalid restaurant location.'})

    item = MenuItem.objects.create(
        merchant=request.user,
        restaurant_location=restaurant_location,
        name=name,
        description=description,
        price=float(price),
        image=image_url
    )
    return JsonResponse({
        'success': True,
        'item_id': item.id,
        'name': item.name,
        'image_url': item.image
    })

# ==================== API: merchant_create_order ====================
@login_required
@csrf_exempt
def api_merchant_create_order(request):
    """
    Merchant creates a direct delivery order with items.
    Due time is auto-calculated from distance.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False})

    data = json.loads(request.body)
    items = data.get('items', [])
    destination_id = data.get('destination_id')

    # Get merchant's restaurant location from first menu item
    first_item = None
    restaurant_location = None
    if items:
        first_item = MenuItem.objects.filter(id=items[0]['id'], merchant=request.user).select_related('restaurant_location').first()
    if first_item and first_item.restaurant_location:
        restaurant_location = first_item.restaurant_location
    else:
        # Fallback: try to find any menu item with restaurant location
        mi = MenuItem.objects.filter(merchant=request.user, restaurant_location__isnull=False).first()
        if mi:
            restaurant_location = mi.restaurant_location

    destination = Location.objects.get(id=destination_id)

    # Auto-calculate due time
    if restaurant_location:
        due_time = calculate_due_time(restaurant_location.matrix_id, destination.matrix_id)
    else:
        due_time = datetime.now() + timedelta(hours=2)

    order = Order.objects.create(
        merchant=request.user,
        customer=request.user,
        destination_id=destination_id,
        restaurant_location=restaurant_location,
        due_time=due_time,
        notes=data.get('notes', ''),
        status='PENDING_MERCHANT'
    )

    for entry in items:
        menu_item = MenuItem.objects.get(id=entry['id'], merchant=request.user)
        OrderItem.objects.create(order=order, menu_item=menu_item, quantity=entry['quantity'])

    return JsonResponse({
        'success': True,
        'order_id': order.id,
        'due_time': order.due_time.isoformat()
    })

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
            'restaurant': o.restaurant_location.name if o.restaurant_location else 'Unknown',
            'restaurant_matrix_id': o.restaurant_location.matrix_id if o.restaurant_location else 0,
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
    Runs nearest-neighbor feasibility check against due times using actual restaurant locations.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})
    data = json.loads(request.body)
    order_ids = data.get('order_ids', [])

    if not order_ids:
        return JsonResponse({'success': False, 'error': 'No orders selected.'})

    orders = list(Order.objects.filter(id__in=order_ids, status='READY_FOR_PICKUP', courier__isnull=True).select_related('restaurant_location', 'destination'))
    if len(orders) != len(order_ids):
        return JsonResponse({'success': False, 'error': 'Some orders are no longer available.'})

    # Determine start location: if all orders from same restaurant, use that; otherwise use first
    restaurant_ids = set()
    for o in orders:
        if o.restaurant_location:
            restaurant_ids.add(o.restaurant_location.matrix_id)

    if len(restaurant_ids) == 1:
        start_id = list(restaurant_ids)[0]
    elif len(restaurant_ids) > 1:
        # Multiple restaurants - use first as start, include others as stops
        start_id = list(restaurant_ids)[0]
    else:
        start_id = 0  # fallback

    destination_ids = []
    due_times = {}
    for o in orders:
        if o.destination:
            mid = o.destination.matrix_id
            # If multiple restaurants, include other restaurants as intermediate stops
            if o.restaurant_location and o.restaurant_location.matrix_id != start_id:
                # Add restaurant as a stop before its destination
                rest_mid = o.restaurant_location.matrix_id
                if rest_mid not in destination_ids:
                    destination_ids.append(rest_mid)
                    due_times[rest_mid] = o.due_time
            if mid not in destination_ids:
                destination_ids.append(mid)
            due = o.due_time
            if due is not None and hasattr(due, 'tzinfo') and due.tzinfo is not None:
                due = due.replace(tzinfo=None)
            due_times[mid] = due

    start_time = datetime.now()

    is_feasible, route, details = validate_route_feasibility(start_id, destination_ids, due_times, start_time)

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
        order.delivered_at = datetime.now()
    order.save()
    return JsonResponse({'success': True})

# ==================== API: courier_route ====================
@login_required
def api_courier_route(request):
    """Return active route data for map visualization, merging all active orders."""
    orders = Order.objects.filter(courier=request.user).exclude(status='DELIVERED')
    if not orders.exists():
        return JsonResponse({'success': False, 'error': 'No active deliveries.'})

    # Merge route data from all active orders
    all_routes = []
    all_details = []
    seen_stops = set()

    for order in orders:
        rd = order.route_data
        if rd:
            route = rd.get('route', [])
            details = rd.get('details', [])
            for stop in route:
                if stop not in seen_stops:
                    all_routes.append(stop)
                    seen_stops.add(stop)
            for detail in details:
                if detail.get('matrix_id') not in [d.get('matrix_id') for d in all_details]:
                    all_details.append(detail)

    if not all_routes:
        # Fallback to first order's route_data
        rd = orders.first().route_data
        all_routes = rd.get('route', []) if rd else []
        all_details = rd.get('details', []) if rd else []

    return JsonResponse({
        'success': True,
        'locations': LOCATIONS_DATA,
        'route': all_routes,
        'details': all_details
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

# ==================== API: admin_create_user ====================
@login_required
@csrf_exempt
def api_admin_create_user(request):
    """
    Admin creates any user with specified role.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})

    if request.user.userprofile.role != 'ADMIN':
        return JsonResponse({'error': 'Forbidden'}, status=403)

    data = json.loads(request.body)
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'CUSTOMER')

    if not username or not password:
        return JsonResponse({'success': False, 'error': 'Username and password are required.'})

    if User.objects.filter(username=username).exists():
        return JsonResponse({'success': False, 'error': 'Username already exists.'})

    user = User.objects.create_user(username=username, email=email, password=password)

    profile, created = UserProfile.objects.get_or_create(user=user)
    profile.role = role
    profile.is_approved = True if role == 'CUSTOMER' else True
    profile.save()

    return JsonResponse({
        'success': True, 
        'message': f'User {username} created successfully as {role}.',
        'user_id': user.id
    })

# ==================== API: admin_delete_user ====================
@login_required
@csrf_exempt
def api_admin_delete_user(request):
    """
    Admin deletes any user.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})

    if request.user.userprofile.role != 'ADMIN':
        return JsonResponse({'error': 'Forbidden'}, status=403)

    data = json.loads(request.body)
    user_id = data.get('user_id')

    try:
        user = User.objects.get(id=user_id)
        if user == request.user:
            return JsonResponse({'success': False, 'error': 'You cannot delete your own account.'})

        username = user.username
        user.delete()
        return JsonResponse({'success': True, 'message': f'User {username} deleted successfully.'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found.'})

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
        'restaurant': o.restaurant_location.name if o.restaurant_location else 'Unknown',
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